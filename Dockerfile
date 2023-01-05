#base image
FROM python:3.8
LABEL org.opencontainers.image.source https://github.com/serengil/deepface
# -----------------------------------
# create required folder
RUN mkdir /app
RUN mkdir /app/api
RUN mkdir /app/deepface
# -----------------------------------
# Copy required files from repo into image
COPY ./deepface /app/deepface
COPY ./api/api.py /app/
COPY ./setup.py /app/
COPY ./README.md /app/
# -----------------------------------
# switch to application directory
WORKDIR /app
# -----------------------------------
# update image os
RUN apt-get update
RUN apt-get install ffmpeg libsm6 libxext6 -y
# -----------------------------------
# install deepface from pypi release (might be out-of-the-date)
# RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org deepface
# -----------------------------------
# install deepface from source code (always up-to-date)
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org -e .
# -----------------------------------
# some packages are optional in deepface. activate if your task depends on one.
# RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org cmake==3.24.1.1
# RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org dlib==19.20.0
# RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host=files.pythonhosted.org lightgbm==2.3.1
# -----------------------------------
# environment variables
ENV PYTHONUNBUFFERED=1
# -----------------------------------
# run the app (re-configure port if necessary)
EXPOSE 5000
# flask run is not recommended in production, move this to gunicorn
CMD ["python", "/app/api.py", "--port", "5000"]