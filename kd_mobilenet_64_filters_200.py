# -*- coding: utf-8 -*-
"""KD_mobilenet2.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1Kjka6hAEkwfAIYRwRp1pGI4InhR_34oS
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

teacher_model_trained = load_model("/home/u248490/resize_720/teacher_model_128.keras")

student_model1= PSPNet(backbone_name='mobilenet',
                       classes= 7, input_shape=(720, 720, 3),
                       activation='softmax',
                       encoder_weights= None,
                       downsample_factor= 4,
                       psp_conv_filters = 64,
                       psp_pooling_type='avg',
                       psp_dropout=None,
                       psp_use_batchnorm=False
                       )

class Distiller(keras.Model):
    def __init__(self, student, teacher):
        super().__init__()
        self.teacher = teacher
        self.student = student

    def compile(
        self,
        optimizer,
        metrics,
        student_loss_fn,
        distillation_loss_fn,
        alpha=0.1,
        temperature=3,
    ):
        """ Configure the distiller.

        Args:
            optimizer: Keras optimizer for the student weights
            metrics: Keras metrics for evaluation
            student_loss_fn: Loss function of difference between student
                predictions and ground-truth
            distillation_loss_fn: Loss function of difference between soft
                student predictions and soft teacher predictions
            alpha: weight to student_loss_fn and 1-alpha to distillation_loss_fn
            temperature: Temperature for softening probability distributions.
                Larger temperature gives softer distributions.
        """
        super().compile(optimizer=optimizer, metrics=metrics)
        self.student_loss_fn = student_loss_fn
        self.distillation_loss_fn = distillation_loss_fn
        self.alpha = alpha
        self.temperature = temperature

    def train_step(self, data):
        # Unpack data
        x, y = data

        # Forward pass of teacher
        teacher_predictions = self.teacher(x, training=False)

        with tf.GradientTape() as tape:
            # Forward pass of student
            student_predictions = self.student(x, training=True)

            # Compute losses
            student_loss = self.student_loss_fn(y, student_predictions)

            # Compute scaled distillation loss from https://arxiv.org/abs/1503.02531
            # The magnitudes of the gradients produced by the soft targets scale
            # as 1/T^2, multiply them by T^2 when using both hard and soft targets.
            distillation_loss = (
                self.distillation_loss_fn(
                    tf.nn.softmax(teacher_predictions / self.temperature, axis=1),
                    tf.nn.softmax(student_predictions / self.temperature, axis=1),
                )
                * self.temperature**2
            )

            loss = self.alpha * student_loss + (1 - self.alpha) * distillation_loss

        # Compute gradients
        trainable_vars = self.student.trainable_variables
        gradients = tape.gradient(loss, trainable_vars)

        # Update weights
        self.optimizer.apply_gradients(zip(gradients, trainable_vars))

        # Update the metrics configured in `compile()`.
        self.compiled_metrics.update_state(y, student_predictions)

        # Return a dict of performance
        results = {m.name: m.result() for m in self.metrics}
        results.update(
            {"student_loss": student_loss, "distillation_loss": distillation_loss}
        )
        return results

    def test_step(self, data):
        # Unpack the data
        x, y = data

        # Compute predictions
        y_prediction = self.student(x, training=False)

        # Calculate the loss
        student_loss = self.student_loss_fn(y, y_prediction)

        # Update the metrics.
        self.compiled_metrics.update_state(y, y_prediction)

        # Return a dict of performance
        results = {m.name: m.result() for m in self.metrics}
        results.update({"student_loss": student_loss})
        return results

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
distiller = Distiller(student=student_model1, teacher=teacher_model_trained )
distiller.compile(
    optimizer=optimizer,
    metrics=[tf.keras.metrics.OneHotMeanIoU(num_classes=num_classes)],
    student_loss_fn=tf.keras.losses.CategoricalFocalCrossentropy(),
    distillation_loss_fn= tf.keras.losses.KLDivergence(),
    alpha=0.1,
    temperature=10
)

history = distiller.fit(X_train, y_train,
              validation_data=(X_val, y_val),
              epochs=200)

