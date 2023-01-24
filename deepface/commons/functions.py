import os
import numpy as np
import pandas as pd
import cv2
import base64
from pathlib import Path
from PIL import Image
import requests

from deepface.detectors import FaceDetector

import tensorflow as tf
tf_version = tf.__version__
tf_major_version = int(tf_version.split(".")[0])
tf_minor_version = int(tf_version.split(".")[1])

if tf_major_version == 1:
	import keras
	from keras.preprocessing.image import load_img, save_img, img_to_array
	from keras.applications.imagenet_utils import preprocess_input
	from keras.preprocessing import image
elif tf_major_version == 2:
	from tensorflow import keras
	from tensorflow.keras.preprocessing.image import load_img, save_img, img_to_array
	from tensorflow.keras.applications.imagenet_utils import preprocess_input
	from tensorflow.keras.preprocessing import image

#--------------------------------------------------

def initialize_folder():
	home = get_deepface_home()

	if not os.path.exists(home+"/.deepface"):
		os.makedirs(home+"/.deepface")
		print("Directory ", home, "/.deepface created")

	if not os.path.exists(home+"/.deepface/weights"):
		os.makedirs(home+"/.deepface/weights")
		print("Directory ", home, "/.deepface/weights created")

def get_deepface_home():
	return str(os.getenv('DEEPFACE_HOME', default=Path.home()))

#--------------------------------------------------

def loadBase64Img(uri):
   encoded_data = uri.split(',')[1]
   nparr = np.fromstring(base64.b64decode(encoded_data), np.uint8)
   img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
   return img

def load_image(img):
	exact_image = False; base64_img = False; url_img = False

	if type(img).__module__ == np.__name__:
		exact_image = True

	elif len(img) > 11 and img[0:11] == "data:image/":
		base64_img = True

	elif len(img) > 11 and img.startswith("http"):
		url_img = True

	#---------------------------

	if base64_img == True:
		img = loadBase64Img(img)

	elif url_img:
		img = np.array(Image.open(requests.get(img, stream=True).raw).convert('RGB'))

	elif exact_image != True: #image path passed as input
		if os.path.isfile(img) != True:
			raise ValueError("Confirm that ",img," exists")

		img = cv2.imread(img)

	return img

#--------------------------------------------------

def extract_faces(img, target_size=(224, 224), detector_backend = 'opencv', grayscale = False, enforce_detection = True, align = True):

	# this is going to store a list of img itself (numpy), it region and confidence
	extracted_faces = []

	#img might be path, base64 or numpy array. Convert it to numpy whatever it is.
	img = load_image(img)
	img_region = [0, 0, img.shape[1], img.shape[0]]

	if detector_backend == 'skip':
		face_objs = [(img, img_region, 0)]
	else:
		face_detector = FaceDetector.build_model(detector_backend)
		face_objs = FaceDetector.detect_faces(face_detector, detector_backend, img, align)

	# in case of no face found
	if len(face_objs) == 0 and enforce_detection == True:
		raise ValueError("Face could not be detected. Please confirm that the picture is a face photo or consider to set enforce_detection param to False.")
	elif len(face_objs) == 0 and enforce_detection == False:
		face_objs = [(img, img_region, 0)]

	for current_img, current_region, confidence in face_objs:
		if current_img.shape[0] > 0 and current_img.shape[1] > 0:

			if grayscale == True:
				current_img = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)

			# resize and padding
			if current_img.shape[0] > 0 and current_img.shape[1] > 0:
				factor_0 = target_size[0] / current_img.shape[0]
				factor_1 = target_size[1] / current_img.shape[1]
				factor = min(factor_0, factor_1)

				dsize = (int(current_img.shape[1] * factor), int(current_img.shape[0] * factor))
				current_img = cv2.resize(current_img, dsize)

				diff_0 = target_size[0] - current_img.shape[0]
				diff_1 = target_size[1] - current_img.shape[1]
				if grayscale == False:
					# Put the base image in the middle of the padded image
					current_img = np.pad(current_img, ((diff_0 // 2, diff_0 - diff_0 // 2), (diff_1 // 2, diff_1 - diff_1 // 2), (0, 0)), 'constant')
				else:
					current_img = np.pad(current_img, ((diff_0 // 2, diff_0 - diff_0 // 2), (diff_1 // 2, diff_1 - diff_1 // 2)), 'constant')
			
			#double check: if target image is not still the same size with target.
			if current_img.shape[0:2] != target_size:
				current_img = cv2.resize(current_img, target_size)
			
			#normalizing the image pixels
			img_pixels = image.img_to_array(current_img) #what this line doing? must?
			img_pixels = np.expand_dims(img_pixels, axis = 0)
			img_pixels /= 255 #normalize input in [0, 1]

			#int cast is for the exception - object of type 'float32' is not JSON serializable
			region_obj = {"x": int(current_region[0]), "y": int(current_region[1]), "w": int(current_region[2]), "h": int(current_region[3])}

			extracted_face = [img_pixels, region_obj, confidence]
			extracted_faces.append(extracted_face)
	
	if len(extracted_faces) == 0 and enforce_detection == True:
		raise ValueError("Detected face shape is ", img.shape,". Consider to set enforce_detection argument to False.")
	
	return extracted_faces

def normalize_input(img, normalization = 'base'):

	#issue 131 declares that some normalization techniques improves the accuracy

	if normalization == 'base':
		return img
	else:
		#@trevorgribble and @davedgd contributed this feature

		img *= 255 #restore input in scale of [0, 255] because it was normalized in scale of  [0, 1] in preprocess_face

		if normalization == 'raw':
			pass #return just restored pixels

		elif normalization == 'Facenet':
			mean, std = img.mean(), img.std()
			img = (img - mean) / std

		elif(normalization=="Facenet2018"):
			# simply / 127.5 - 1 (similar to facenet 2018 model preprocessing step as @iamrishab posted)
			img /= 127.5
			img -= 1

		elif normalization == 'VGGFace':
			# mean subtraction based on VGGFace1 training data
			img[..., 0] -= 93.5940
			img[..., 1] -= 104.7624
			img[..., 2] -= 129.1863

		elif(normalization == 'VGGFace2'):
			# mean subtraction based on VGGFace2 training data
			img[..., 0] -= 91.4953
			img[..., 1] -= 103.8827
			img[..., 2] -= 131.0912

		elif(normalization == 'ArcFace'):
			#Reference study: The faces are cropped and resized to 112×112,
			#and each pixel (ranged between [0, 255]) in RGB images is normalised
			#by subtracting 127.5 then divided by 128.
			img -= 127.5
			img /= 128

	#-----------------------------

	return img

def find_target_size(model_name):

	target_sizes = {
		"VGG-Face": (224, 224),
		"Facenet": (160, 160),
		"Facenet512": (160, 160),
		"OpenFace": (96, 96),
		"DeepFace": (152, 152),
		"DeepID": (47, 55),
		"Dlib": (150, 150),
		"ArcFace": (112, 112),
		"SFace": (112, 112)
	}

	if model_name not in target_sizes.keys():
		raise ValueError(f"unimplemented model name - {model_name}")
	
	return target_sizes[model_name]
