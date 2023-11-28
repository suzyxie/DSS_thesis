# -*- coding: utf-8 -*-
"""mobilenet_no_KD_16.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/185xeMF5nXF-pq4jssoi4KO42q9KcuCMC
"""

import os
import numpy as np
import tensorflow as tf
from tensorflow.keras.optimizers.schedules import PolynomialDecay
from tensorflow import keras
from tensorflow.keras.losses import CategoricalFocalCrossentropy,KLDivergence
from tensorflow.keras.callbacks import Callback
from tensorflow.keras.metrics import OneHotMeanIoU
from tensorflow.keras.models import load_model
from tensorflow.keras import layers

os.environ["SM_FRAMEWORK"] = "tf.keras"

from tensorflow import keras
import segmentation_models as sm
from segmentation_models import PSPNet

X_train = np.load('/home/u248490/resize_720/X_train_720.npy')
y_train = np.load('/home/u248490/resize_720/y_train_720.npy')
X_val = np.load('/home/u248490/resize_720/X_val_720.npy')
y_val = np.load("/home/u248490/resize_720/y_val_720.npy")

num_classes = 7
y_train_reshaped = np.zeros((y_train.shape[0], y_train.shape[1], y_train.shape[2], num_classes), dtype=np.uint8)

# Iterate over each class and create the respective channel
for class_idx in range(num_classes):
    y_train_reshaped[:, :, :, class_idx] = (y_train == class_idx).astype(np.uint8)


X_train = X_train.astype('float32')
y_train = y_train_reshaped.astype('float32')

y_val_reshaped = np.zeros((y_val.shape[0], y_val.shape[1], y_val.shape[2], num_classes), dtype=np.uint8)

# Iterate over each class and create the respective channel
for class_idx in range(num_classes):
    y_val_reshaped[:, :, :, class_idx] = (y_val == class_idx).astype(np.uint8)

X_val = X_val.astype('float32')
y_val = y_val_reshaped.astype('float32')

student_model = PSPNet(backbone_name='mobilenet',
                       classes= 7, input_shape=(720, 720, 3),
                       activation='softmax',
                       encoder_weights= 'imagenet',
                       downsample_factor= 4,
                       psp_conv_filters = 16,
                       psp_pooling_type='avg',
                       psp_dropout=None,
                       )

# Define your learning rate schedule with the given parameters
base_learning_rate = 0.0001
momentum = 0.9
weight_decay = 0.0001
power = 0.9
auxiliary_loss_weight = 0.4

# Calculate the total number of training steps (you need to adjust this based on your dataset and batch size)
total_steps = 10000

learning_rate_schedule = PolynomialDecay(
    initial_learning_rate=base_learning_rate,
    decay_steps=total_steps,
    end_learning_rate=0,  # You can set this to 0 or any other final learning rate you desire
    power=power
)

# Create the legacy Adam optimizer with the specified momentum and weight decay
optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate_schedule, beta_1=momentum, beta_2=0.999, epsilon=1e-7, weight_decay=weight_decay)

# Compile your model using the custom optimizer and loss
student_model.compile(optimizer=optimizer, loss=tf.keras.losses.CategoricalFocalCrossentropy(),
                      metrics=[tf.keras.metrics.OneHotMeanIoU(num_classes=num_classes)])

history = student_model.fit(X_train, y_train,
                            validation_data=(X_val, y_val),
                            epochs= 100
                            )
