# -*- coding: utf-8 -*-


import pickle as pkl
import tensorflow as tf
import pandas as pd
import numpy as np
import math
import os
import numpy.linalg as la
from input_data_assist_simple import preprocess_data,load_szassist_data
from ktgcn import ktgcnCell
#from gru import GRUCell 

from visualization import plot_result,plot_error
from sklearn.metrics import mean_squared_error,mean_absolute_error
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
#import time

class KSTGCNPlugin:
 def input(self, inputfile):
  self.inputfile = inputfile
 def run(self):
     pass
 def output(self, outputfile):
  model_name = 'ktgcn'
  data_name = 'sz'
  train_rate =  0.8
  seq_len = 10
  output_dim = pre_len =1
  batch_size = 64
  lr = 0.001
  training_epoch = 3
  gru_units = 64
  dim = 20
  attribute = 'kg'
  noise_name = 'Possion'
  methods = 'none'
  ###### load data ######
  if data_name == 'sz':
    data, adj = load_szassist_data('sz', self.inputfile)


  def MaxMinNormalization(x,Max,Min):
    x = (x-Min)/(Max-Min);
    return x
  PG = 1
  if noise_name == 'Gauss':
    Gauss = np.random.normal(0,PG,size=data.shape)
    noise_Gauss = MaxMinNormalization(Gauss,np.max(Gauss),np.min(Gauss))
    data = data + noise_Gauss
  elif noise_name == 'Possion':
    Possion = np.random.poisson(PG,size=data.shape)
    noise_Possion = MaxMinNormalization(Possion,np.max(Possion),np.min(Possion))
    data = data + noise_Possion
  else:
    PG = 'None-TransR'
    
  time_len = data.shape[0]
  num_nodes = data.shape[1]
  data1 =np.mat(data,dtype=np.float32)

  #### normalization
  max_value = np.max(data1)
  data1  = data1/max_value

  if methods == 'add kg':
    name = 'add kg dim'
  else:
    name = 'ktgcn'
    
  trainX, trainY, testX, testY = preprocess_data(data1, time_len, train_rate, seq_len, pre_len,methods,attribute,self.inputfile)

  totalbatch = int(trainX.shape[0]/batch_size)
  training_data_count = len(trainX)

  def KTGCN(_X, _weights, _biases):
    ###
    cell_1 = ktgcnCell(self.inputfile, gru_units, adj, num_nodes=num_nodes, dim = dim,time_len=time_len)
    cell = tf.nn.rnn_cell.MultiRNNCell([cell_1], state_is_tuple=True)
    _X = tf.unstack(_X, axis=1)
    outputs, states = tf.nn.static_rnn(cell, _X, dtype=tf.float32)
    print('outputs_shape:',outputs)
    print('states_shape:',states)
    m = []
    for i in outputs:
        o = tf.reshape(i,shape=[-1,num_nodes,gru_units])
        o = tf.reshape(o,shape=[-1,gru_units])
        m.append(o)
    last_output = m[-1]
    output = tf.matmul(last_output, _weights['out']) + _biases['out']
    output = tf.reshape(output,shape=[-1,num_nodes,pre_len])
    output = tf.transpose(output, perm=[0,2,1])
    output = tf.reshape(output, shape=[-1,num_nodes])
    return output, m, states
    
    
  ###### placeholders ######
  if methods == 'add kg':
    inputs = tf.placeholder(tf.float32, shape=[None, seq_len*2+pre_len+1, num_nodes])
  else:
    inputs = tf.placeholder(tf.float32, shape=[None, seq_len, num_nodes])
  labels = tf.placeholder(tf.float32, shape=[None, pre_len, num_nodes])

  # Graph weights
  weights = {
    'out': tf.Variable(tf.random_normal([gru_units, pre_len], mean=1.0), name='weight_o')}
  biases = {
    'out': tf.Variable(tf.random_normal([pre_len]),name='bias_o')}

  if model_name == 'ktgcn':
    pred,ttts,ttto = KTGCN(inputs, weights, biases)

  y_pred = pred
      

  ###### optimizer ######
  lambda_loss = 0.0015
  Lreg = lambda_loss * sum(tf.nn.l2_loss(tf_var) for tf_var in tf.trainable_variables())
  label = tf.reshape(labels, [-1,num_nodes])
  ##loss
  print('y_pre_shape:',y_pred.shape)
  print('label_shape:',label.shape)
  loss = tf.reduce_mean(tf.nn.l2_loss(y_pred-label) + Lreg)
  ##rmse
  error = tf.sqrt(tf.reduce_mean(tf.square(y_pred-label)))
  optimizer = tf.train.AdamOptimizer(lr).minimize(loss)

  ###### Initialize session ######
  variables = tf.global_variables()
  saver = tf.train.Saver(tf.global_variables())  
  #sess = tf.Session()
  gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.333)
  sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options))
  sess.run(tf.global_variables_initializer())

  #out = 'out/%s'%(model_name)
  #path1 = '%s_%s_lr%r_batch%r_unit%r_seq%r_pre%r_epoch%r_dim%r_attribute%r_methods%r_PG%r_noise_name%r'%(model_name,data_name,lr,batch_size,gru_units,seq_len,pre_len,training_epoch,dim,attribute,methods,PG,noise_name)
  #path = os.path.join(out,path1)
  path = outputfile
  if not os.path.exists(path):
    os.makedirs(path)
    
  ###### evaluation ######
  def evaluation(a,b):
    rmse = math.sqrt(mean_squared_error(a,b))
    mae = mean_absolute_error(a, b)
    F_norm = la.norm(a-b,'fro')/la.norm(a,'fro')
    r2 = 1-((a-b)**2).sum()/((a-a.mean())**2).sum()
    var = 1-(np.var(a-b))/np.var(a)
    return rmse, mae, 1-F_norm, r2, var
 
   
  x_axe,batch_loss,batch_rmse,batch_pred = [], [], [], []
  test_loss,test_rmse,test_mae,test_acc,test_r2,test_var,test_pred = [],[],[],[],[],[],[]
  
  for epoch in range(training_epoch):
    for m in range(totalbatch):
        mini_batch = trainX[m * batch_size : (m+1) * batch_size]
        mini_label = trainY[m * batch_size : (m+1) * batch_size]
        _, loss1, rmse1, train_output = sess.run([optimizer, loss, error, y_pred],
                                                 feed_dict = {inputs:mini_batch, labels:mini_label})
        batch_loss.append(loss1)
        batch_rmse.append(rmse1 * max_value)

     # Test completely at every epoch
    loss2, rmse2, test_output = sess.run([loss, error, y_pred],
                                         feed_dict = {inputs:testX, labels:testY})
  #    testoutput = np.abs(test_output)
    test_output[test_output<0]=0
    test_label = np.reshape(testY,[-1,num_nodes])
    rmse, mae, acc, r2_score, var_score = evaluation(test_label, test_output)
    test_label1 = test_label * max_value
    test_output1 = test_output * max_value
    test_loss.append(loss2)
    test_rmse.append(rmse * max_value)
    test_mae.append(mae * max_value)
    test_acc.append(acc)
    test_r2.append(r2_score)
    test_var.append(var_score)
    test_pred.append(test_output1)
    
    print('Iter:{}'.format(epoch),
          'train_rmse:{:.4}'.format(batch_rmse[-1]),
          'test_loss:{:.4}'.format(loss2),
          'test_rmse:{:.4}'.format(rmse),
          'test_acc:{:.4}'.format(acc))
    
    if (epoch % 500 == 0):        
        saver.save(sess, path+'/model_100/TGCN_pre_%r'%epoch, global_step = epoch)
        
  ############## visualization ###############
  #x = [i for i in range(training_epoch)]
  b = int(len(batch_rmse)/totalbatch)
  batch_rmse1 = [i for i in batch_rmse]
  train_rmse = [(sum(batch_rmse1[i*totalbatch:(i+1)*totalbatch])/totalbatch) for i in range(b)]
  batch_loss1 = [i for i in batch_loss]
  train_loss = [(sum(batch_loss1[i*totalbatch:(i+1)*totalbatch])/totalbatch) for i in range(b)]
  #test_rmse = [float(i) for i in test_rmse]

  index = test_rmse.index(np.min(test_rmse))
  test_result = test_pred[index]
  var = pd.DataFrame(test_result)
  var.to_csv(path+'/test_result.csv',index = False,header = False)
  plot_result(test_result,test_label1,path)
  plot_error(train_rmse,train_loss,test_rmse,test_acc,test_mae,path)
  evalution = []
  evalution.append(np.min(test_rmse))
  evalution.append(test_mae[index])
  evalution.append(test_acc[index])
  evalution.append(test_r2[index])
  evalution.append(test_var[index])
  evalution = pd.DataFrame(evalution)
  evalution.to_csv(path+'/evalution.csv',index=False,header=None)
  print('min_rmse:%r'%(np.min(test_rmse)),
      'min_mae:%r'%(test_mae[index]),
      'max_acc:%r'%(test_acc[index]),
      'r2:%r'%(test_r2[index]),
      'var:%r'%test_var[index])
