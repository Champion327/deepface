import warnings
warnings.filterwarnings("ignore")

import os
#os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import time
from os import path
import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm
import pickle

from deepface.basemodels import VGGFace, OpenFace, Facenet, Facenet512, FbDeepFace, DeepID, DlibWrapper, ArcFace, SFace
from deepface.extendedmodels import Age, Gender, Race, Emotion
from deepface.commons import functions, realtime, distance as dst

import tensorflow as tf
tf_version = int(tf.__version__.split(".")[0])
if tf_version == 2:
	import logging
	tf.get_logger().setLevel(logging.ERROR)

def build_model(model_name):

	"""
	This function builds a deepface model
	Parameters:
		model_name (string): face recognition or facial attribute model
			VGG-Face, Facenet, OpenFace, DeepFace, DeepID for face recognition
			Age, Gender, Emotion, Race for facial attributes

	Returns:
		built deepface model
	"""

	global model_obj #singleton design pattern

	models = {
		'VGG-Face': VGGFace.loadModel,
		'OpenFace': OpenFace.loadModel,
		'Facenet': Facenet.loadModel,
		'Facenet512': Facenet512.loadModel,
		'DeepFace': FbDeepFace.loadModel,
		'DeepID': DeepID.loadModel,
		'Dlib': DlibWrapper.loadModel,
		'ArcFace': ArcFace.loadModel,
		'SFace': SFace.load_model,
		'Emotion': Emotion.loadModel,
		'Age': Age.loadModel,
		'Gender': Gender.loadModel,
		'Race': Race.loadModel
	}

	if not "model_obj" in globals():
		model_obj = {}

	if not model_name in model_obj.keys():
		model = models.get(model_name)
		if model:
			model = model()
			model_obj[model_name] = model
			#print(model_name," built")
		else:
			raise ValueError('Invalid model_name passed - {}'.format(model_name))

	return model_obj[model_name]

def verify(img1_path, img2_path, model_name = 'VGG-Face', detector_backend = 'opencv', distance_metric = 'cosine', enforce_detection = True, align = True, normalization = 'base'):

	"""
	This function verifies an image pair is same person or different persons. In the background, verification function represents facial images as vectors and then calculates the similarity between those vectors. Vectors of same person images should have more similarity (or less distance) than vectors of different persons.

	Parameters:
		img1_path, img2_path: exact image path as string. numpy array (BGR) or based64 encoded images are also welcome. 
		If one of pair has more than one face, then we will compare the face pair with max similarity.

		model_name (string): VGG-Face, Facenet, Facenet512, OpenFace, DeepFace, DeepID, Dlib, ArcFace, SFace

		distance_metric (string): cosine, euclidean, euclidean_l2

		enforce_detection (boolean): If no face could not be detected in an image, then this function will return exception by default. 
		Set this to False not to have this exception. This might be convenient for low resolution images.

		detector_backend (string): set face detector backend to opencv, retinaface, mtcnn, ssd, dlib or mediapipe

	Returns:
		Verify function returns a dictionary. If img1_path is a list of image pairs, then the function will return list of dictionary.

		{
			"verified": True
			, "distance": 0.2563
			, "max_threshold_to_verify": 0.40
			, "model": "VGG-Face"
			, "similarity_metric": "cosine"
			, 'facial_areas': {
				'img1': {'x': 345, 'y': 211, 'w': 769, 'h': 769}, 
				'img2': {'x': 318, 'y': 534, 'w': 779, 'h': 779}
			}
			, "time": 2
		}

	"""

	tic = time.time()

	#--------------------------------
	target_size = functions.find_target_size(model_name=model_name)

	# img pairs might have many faces
	img1_objs = functions.extract_faces(
		img = img1_path, 
		target_size = (target_size[1], target_size[0]), 
		detector_backend = detector_backend, 
		grayscale = False, 
		enforce_detection = enforce_detection, 
		align = align)
	
	img2_objs = functions.extract_faces(
		img = img2_path, 
		target_size = (target_size[1], target_size[0]), 
		detector_backend = detector_backend, 
		grayscale = False, 
		enforce_detection = enforce_detection, 
		align = align)
	#--------------------------------
	distances = []
	regions = []
	# now we will find the face pair with minimum distance
	for img1_content, img1_region, img1_confidence in img1_objs:
		for img2_content, img2_region, img2_confidence in img2_objs:
			img1_embedding_obj = represent(img_path = img1_content
						, model_name = model_name
						, enforce_detection = enforce_detection
						, detector_backend = "skip"
						, align = align
						, normalization = normalization
						)
			
			img2_embedding_obj = represent(img_path = img2_content
						, model_name = model_name
						, enforce_detection = enforce_detection
						, detector_backend = "skip"
						, align = align
						, normalization = normalization
						)
			
			img1_representation = img1_embedding_obj[0]["embedding"]
			img2_representation = img2_embedding_obj[0]["embedding"]
			
			if distance_metric == 'cosine':
				distance = dst.findCosineDistance(img1_representation, img2_representation)
			elif distance_metric == 'euclidean':
				distance = dst.findEuclideanDistance(img1_representation, img2_representation)
			elif distance_metric == 'euclidean_l2':
				distance = dst.findEuclideanDistance(dst.l2_normalize(img1_representation), dst.l2_normalize(img2_representation))
			else:
				raise ValueError("Invalid distance_metric passed - ", distance_metric)
			
			distances.append(distance)
			regions.append((img1_region, img2_region))

	# -------------------------------
	threshold = dst.findThreshold(model_name, distance_metric)
	distance = min(distances) #best distance
	facial_areas = regions[np.argmin(distances)]

	toc = time.time()

	resp_obj = {
		"verified": True if distance <= threshold else False
		, "distance": distance
		, "threshold": threshold
		, "model": model_name
		, "detector_backend": detector_backend
		, "similarity_metric": distance_metric
		, "facial_areas": {
			"img1": facial_areas[0],
			"img2": facial_areas[1]
		}
		, "time": round(toc - tic, 2)
	}

	return resp_obj

def analyze(img_path, actions = ('emotion', 'age', 'gender', 'race') , enforce_detection = True, detector_backend = 'opencv', align = True, silent = False):

	"""
	This function analyzes facial attributes including age, gender, emotion and race. In the background, analysis function builds convolutional neural network models to classify age, gender, emotion and race of the input image.

	Parameters:
		img_path: exact image path, numpy array (BGR) or base64 encoded image could be passed.

		actions (tuple): The default is ('age', 'gender', 'emotion', 'race'). You can drop some of those attributes.

		enforce_detection (boolean): The function throws exception if no face detected by default. Set this to False if you don't want to get exception. This might be convenient for low resolution images.

		detector_backend (string): set face detector backend to opencv, retinaface, mtcnn, ssd, dlib or mediapipe.

		silent (boolean): disable (some) log messages

	Returns:
		The function returns a list of dictionaries for each face appearing in the image.

		[
			{
				"region": {'x': 230, 'y': 120, 'w': 36, 'h': 45},
				"age": 28.66,
				"dominant_gender": "Woman",
				"gender": {
					'Woman': 99.99407529830933,
					'Man': 0.005928758764639497,
				}
				"dominant_emotion": "neutral",
				"emotion": {
					'sad': 37.65260875225067,
					'angry': 0.15512987738475204,
					'surprise': 0.0022171278033056296,
					'fear': 1.2489334680140018,
					'happy': 4.609785228967667,
					'disgust': 9.698561953541684e-07,
					'neutral': 56.33133053779602
				}
				"dominant_race": "white",
				"race": {
					'indian': 0.5480832420289516,
					'asian': 0.7830780930817127,
					'latino hispanic': 2.0677512511610985,
					'black': 0.06337375962175429,
					'middle eastern': 3.088453598320484,
					'white': 93.44925880432129
				}
			}
		]
	"""
	#---------------------------------
	# validate actions 
	if type(actions) == str:
		actions = (actions,)

	actions = list(actions)
	#---------------------------------
	# build models
	models = {}
	if 'emotion' in actions:
		models['emotion'] = build_model('Emotion')

	if 'age' in actions:
		models['age'] = build_model('Age')

	if 'gender' in actions:
		models['gender'] = build_model('Gender')

	if 'race' in actions:
		models['race'] = build_model('Race')
	#---------------------------------
	resp_objects = []

	img_objs = functions.extract_faces(img=img_path, target_size=(224, 224), detector_backend=detector_backend, grayscale = False, enforce_detection=enforce_detection, align=align)

	for img_content, img_region, img_confidence in img_objs:
		if img_content.shape[0] > 0 and img_content.shape[1] > 0:
			obj = {}
			#facial attribute analysis
			pbar = tqdm(range(0, len(actions)), desc='Finding actions', disable = silent)
			for index in pbar:
				action = actions[index]
				pbar.set_description("Action: %s" % (action))

				if action == 'emotion':
					img_gray = cv2.cvtColor(img_content[0], cv2.COLOR_BGR2GRAY)
					img_gray = cv2.resize(img_gray, (48, 48))
					img_gray = np.expand_dims(img_gray, axis = 0)

					emotion_predictions = models['emotion'].predict(img_gray, verbose=0)[0,:]

					sum_of_predictions = emotion_predictions.sum()

					obj["emotion"] = {}
					emotion_labels = ['angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral']

					for i in range(0, len(emotion_labels)):
						emotion_label = emotion_labels[i]
						emotion_prediction = 100 * emotion_predictions[i] / sum_of_predictions
						obj["emotion"][emotion_label] = emotion_prediction

					obj["dominant_emotion"] = emotion_labels[np.argmax(emotion_predictions)]

				elif action == 'age':
					age_predictions = models['age'].predict(img_content, verbose=0)[0,:]
					apparent_age = Age.findApparentAge(age_predictions)
					obj["age"] = int(apparent_age) #int cast is for the exception - object of type 'float32' is not JSON serializable

				elif action == 'gender':
					gender_predictions = models['gender'].predict(img_content, verbose=0)[0,:]
					gender_labels = ["Woman", "Man"]
					obj["gender"] = {}
					for i, gender_label in enumerate(gender_labels):
						gender_prediction = 100 * gender_predictions[i]
						obj["gender"][gender_label] = gender_prediction

					obj["dominant_gender"] = gender_labels[np.argmax(gender_predictions)]

				elif action == 'race':
					race_predictions = models['race'].predict(img_content, verbose=0)[0,:]
					sum_of_predictions = race_predictions.sum()

					obj["race"] = {}
					race_labels = ['asian', 'indian', 'black', 'white', 'middle eastern', 'latino hispanic']
					for i in range(0, len(race_labels)):
						race_label = race_labels[i]
						race_prediction = 100 * race_predictions[i] / sum_of_predictions
						obj["race"][race_label] = race_prediction

					obj["dominant_race"] = race_labels[np.argmax(race_predictions)]

				#-----------------------------
				# mention facial areas
				obj["region"] = img_region
				
			resp_objects.append(obj)
	
	return resp_objects	

def find(img_path, db_path, model_name ='VGG-Face', distance_metric = 'cosine', enforce_detection = True, detector_backend = 'opencv', align = True, normalization = 'base', silent=False):

	"""
	This function applies verification several times and find the identities in a database

	Parameters:
		img_path: exact image path, numpy array (BGR) or based64 encoded image. 
		
		db_path (string): You should store some .jpg files in a folder and pass the exact folder path to this.

		model_name (string): VGG-Face, Facenet, Facenet512, OpenFace, DeepFace, DeepID, Dlib, ArcFace, SFace or Ensemble

		distance_metric (string): cosine, euclidean, euclidean_l2

		enforce_detection (boolean): The function throws exception if a face could not be detected. Set this to True if you don't want to get exception. This might be convenient for low resolution images.

		detector_backend (string): set face detector backend to opencv, retinaface, mtcnn, ssd, dlib or mediapipe

		silent (boolean): disable some logging and progress bars

	Returns:
		This function returns list of pandas data frame. Each item of the list corresponding to an identity in the img_path.
	"""

	tic = time.time()

	#-------------------------------
	if os.path.isdir(db_path) != True:
		raise ValueError("Passed db_path does not exist!")
	else:
		target_size = functions.find_target_size(model_name=model_name)

		#---------------------------------------

		file_name = "representations_%s.pkl" % (model_name)
		file_name = file_name.replace("-", "_").lower()

		if path.exists(db_path+"/"+file_name):

			if not silent:
				print("WARNING: Representations for images in ",db_path," folder were previously stored in ", file_name, ". If you added new instances after this file creation, then please delete this file and call find function again. It will create it again.")

			f = open(db_path+'/'+file_name, 'rb')
			representations = pickle.load(f)

			if not silent:
				print("There are ", len(representations)," representations found in ",file_name)

		else: #create representation.pkl from scratch
			employees = []

			for r, d, f in os.walk(db_path): # r=root, d=directories, f = files
				for file in f:
					if ('.jpg' in file.lower()) or ('.jpeg' in file.lower()) or ('.png' in file.lower()):
						exact_path = r + "/" + file
						employees.append(exact_path)

			if len(employees) == 0:
				raise ValueError("There is no image in ", db_path," folder! Validate .jpg or .png files exist in this path.")

			#------------------------
			#find representations for db images

			representations = []

			#for employee in employees:
			pbar = tqdm(range(0,len(employees)), desc='Finding representations', disable = True if silent == True else False)
			for index in pbar:
				employee = employees[index]

				img_objs = functions.extract_faces(img = employee, 
					target_size = target_size, 
					detector_backend = detector_backend, 
					grayscale = False, 
					enforce_detection = enforce_detection, 
					align = align
				)

				for img_content, img_region, img_confidence in img_objs:
					embedding_obj = represent(img_path = img_content
						, model_name = model_name
						, enforce_detection = enforce_detection
						, detector_backend = "skip"
						, align = align
						, normalization = normalization
						)
					
					img_representation = embedding_obj[0]["embedding"]

					instance = []
					instance.append(employee) 
					instance.append(img_representation)
					representations.append(instance)

			#-------------------------------

			f = open(db_path+'/'+file_name, "wb")
			pickle.dump(representations, f)
			f.close()

			if not silent: 
				print("Representations stored in ",db_path,"/",file_name," file. Please delete this file when you add new identities in your database.")

		#----------------------------
		#now, we got representations for facial database
		df = pd.DataFrame(representations, columns = ["identity", f"{model_name}_representation"])

		# img path might have move than once face
		target_objs = functions.extract_faces(img = img_path, 
					target_size = target_size, 
					detector_backend = detector_backend, 
					grayscale = False, 
					enforce_detection = enforce_detection, 
					align = align
				)
		
		resp_obj = []

		for target_img, target_region, target_confidence in target_objs:
			target_embedding_obj = represent(img_path = target_img
						, model_name = model_name
						, enforce_detection = enforce_detection
						, detector_backend = "skip"
						, align = align
						, normalization = normalization
						)
			
			target_representation = target_embedding_obj[0]["embedding"]

			result_df = df.copy() #df will be filtered in each img
			result_df["source_x"] = target_region["x"]
			result_df["source_y"] = target_region["y"]
			result_df["source_w"] = target_region["w"]
			result_df["source_h"] = target_region["h"]

			distances = []
			for index, instance in df.iterrows():
				source_representation = instance[f"{model_name}_representation"]

				if distance_metric == 'cosine':
					distance = dst.findCosineDistance(source_representation, target_representation)
				elif distance_metric == 'euclidean':
					distance = dst.findEuclideanDistance(source_representation, target_representation)
				elif distance_metric == 'euclidean_l2':
					distance = dst.findEuclideanDistance(dst.l2_normalize(source_representation), dst.l2_normalize(target_representation))
				else:
					raise ValueError(f"invalid distance metric passes - {distance_metric}")

				distances.append(distance)

				#---------------------------

			result_df[f"{model_name}_{distance_metric}"] = distances

			threshold = dst.findThreshold(model_name, distance_metric)
			result_df = result_df.drop(columns = [f"{model_name}_representation"])
			result_df = result_df[result_df[f"{model_name}_{distance_metric}"] <= threshold]
			result_df = result_df.sort_values(by = [f"{model_name}_{distance_metric}"], ascending=True).reset_index(drop=True)

			resp_obj.append(result_df)

		# -----------------------------------

		toc = time.time()

		if not silent:
			print("find function lasts ",toc-tic," seconds")

		return resp_obj

def represent(img_path, model_name = 'VGG-Face', model = None, enforce_detection = True, detector_backend = 'opencv', align = True, normalization = 'base'):

	"""
	This function represents facial images as vectors. The function uses convolutional neural networks models to generate vector embeddings.

	Parameters:
		img_path (string): exact image path. Alternatively, numpy array (BGR) or based64 encoded images could be passed.

		enforce_detection (boolean): If any face could not be detected in an image, then verify function will return exception. Set this to False not to have this exception. This might be convenient for low resolution images.

		detector_backend (string): set face detector backend to opencv, retinaface, mtcnn, ssd, dlib or mediapipe

		normalization (string): normalize the input image before feeding to model

	Returns:
		Represent function returns a multidimensional vector. The number of dimensions is changing based on the reference model. E.g. FaceNet returns 128 dimensional vector; VGG-Face returns 2622 dimensional vector.
	"""
	resp_objs = []

	model = build_model(model_name)

	#---------------------------------
	# we started to run pre-process in verification. so, this can be skipped if it is coming from verification.
	if detector_backend != "skip":
		target_size = functions.find_target_size(model_name=model_name)

		img_objs = functions.extract_faces(img = img_path, 
								target_size = target_size, 
								detector_backend = detector_backend, 
								grayscale = False, 
								enforce_detection = enforce_detection, 
								align = align)
	else: # skip
		if type(img_path) == str:
			img = functions.load_image(img_path)
		elif type(img_path).__module__ == np.__name__:
			img = img_path.copy()
		else:
			raise ValueError(f"unexpected type for img_path - {type(img_path)}")
		
		img_region = [0, 0, img.shape[1], img.shape[0]]
		img_objs = [(img, img_region, 0)]
	#---------------------------------

	for img, region, confidence in img_objs:
		#custom normalization
		img = functions.normalize_input(img = img, normalization = normalization)

		#represent
		if "keras" in str(type(model)):
			#new tf versions show progress bar and it is annoying
			embedding = model.predict(img, verbose=0)[0].tolist()
		else:
			#SFace and Dlib are not keras models and no verbose arguments
			embedding = model.predict(img)[0].tolist()
		
		resp_obj = {}
		resp_obj["embedding"] = embedding
		resp_obj["facial_area"] = region
		resp_objs.append(resp_obj)

	return resp_objs

def stream(db_path = '', model_name ='VGG-Face', detector_backend = 'opencv', distance_metric = 'cosine', enable_face_analysis = True, source = 0, time_threshold = 5, frame_threshold = 5):

	"""
	This function applies real time face recognition and facial attribute analysis

	Parameters:
		db_path (string): facial database path. You should store some .jpg files in this folder.

		model_name (string): VGG-Face, Facenet, Facenet512, OpenFace, DeepFace, DeepID, Dlib, ArcFace, SFace or Ensemble

		detector_backend (string): opencv, retinaface, mtcnn, ssd, dlib or mediapipe

		distance_metric (string): cosine, euclidean, euclidean_l2

		enable_facial_analysis (boolean): Set this to False to just run face recognition

		source: Set this to 0 for access web cam. Otherwise, pass exact video path.

		time_threshold (int): how many second analyzed image will be displayed

		frame_threshold (int): how many frames required to focus on face

	"""

	if time_threshold < 1:
		raise ValueError("time_threshold must be greater than the value 1 but you passed "+str(time_threshold))

	if frame_threshold < 1:
		raise ValueError("frame_threshold must be greater than the value 1 but you passed "+str(frame_threshold))

	realtime.analysis(db_path, model_name, detector_backend, distance_metric, enable_face_analysis
						, source = source, time_threshold = time_threshold, frame_threshold = frame_threshold)

def extract_faces(img_path, target_size = (224, 224), detector_backend = 'opencv', enforce_detection = True, align = True):

	"""
	This function applies pre-processing stages of a face recognition pipeline including detection and alignment

	Parameters:
		img_path: exact image path, numpy array (BGR) or base64 encoded image

		target_size (tuple): final shape of facial image. black pixels will be added to resize the image.

		detector_backend (string): face detection backends are retinaface, mtcnn, opencv, ssd or dlib

		enforce_detection (boolean): function throws exception if face cannot be detected in the fed image. 
		Set this to False if you do not want to get exception and run the function anyway.

		align (boolean): alignment according to the eye positions.

	Returns:
		list of dictionaries. Each dictionary will have facial image itself, extracted area from the original image and confidence score.

	"""
	
	resp_objs = []
	img_objs = functions.extract_faces(
						img = img_path, 
						target_size = target_size, 
						detector_backend = detector_backend, 
						grayscale = False, 
						enforce_detection = enforce_detection, 
						align = align
					)

	for img, region, confidence in img_objs:
		resp_obj = {}

		# discard expanded dimension
		if len(img.shape) == 4:
			img = img[0]

		resp_obj["face"] = img[:, :, ::-1]
		resp_obj["facial_area"] = region
		resp_obj["confidence"] = confidence
		resp_objs.append(resp_obj)
	
	return resp_objs

#---------------------------
#main

functions.initialize_folder()

def cli():
	import fire
	fire.Fire()
