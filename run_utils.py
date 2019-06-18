import tensorflow as tf
import os
import cv2
import numpy as np

class run:
    def __init__(self, config, ckpt_path, LR_holder, HR_holder):
        self.config = config
        self.LR_holder = LR_holder
        self.HR_holder = HR_holder
        self.ckpt_path = ckpt_path

    def train(self, X, Y, epochs, batch, load_flag, model_outputs):
        out, loss, train_op, psnr = model_outputs
        
        nr_training_instances = len(X)
        num_of_batches = nr_training_instances//batch
        print("Number of batches: {}".format(num_of_batches))

        # -- Training session
        with tf.Session(config=self.config) as sess:
            
            train_writer = tf.summary.FileWriter('./logs/train', sess.graph)
            sess.run(tf.global_variables_initializer())
            
            # Make saver instance
            saver = tf.train.Saver()
            
            # Create check points directory
            if not os.path.exists(self.ckpt_path):
                os.makedirs(self.ckpt_path)
            else:
                if os.path.isfile(self.ckpt_path + "fsrcnn_ckpt" + ".meta"):
                    if load_flag:
                        saver.restore(sess, tf.train.latest_checkpoint(self.ckpt_path))
                        print("Loaded checkpoint.")
                    if not load_flag:
                        print("No checkpoint loaded. Training from scratch.")
                else:
                    print("Previous checkpoint does not exists.")

            print("Training...")
            for e in range(1,epochs+1):
                
                count, train_loss, train_psnr = 0, 0, 0
                
                try:
                    for b in range(0, num_of_batches):
                        
                        next_input_batch = X[b*batch:(b*batch) + batch]
                        next_label_batch = Y[b*batch:(b*batch) + batch]
                        
                        o, l, t, ps = sess.run([out, loss, train_op, psnr], feed_dict={self.LR_holder: next_input_batch, 
                                                                                       self.HR_holder: next_label_batch})

                        train_loss += l
                        train_psnr += ps
                        count += 1
                        
                        if(count % 1000 == 0):
                            print("Batch no: [{}/{}]".format(count, num_of_batches))
                    
                    # Average psnr
                    total_psnr = 0
                    for p in train_psnr:
                        total_psnr += p
                    total_psnr /= batch

                    print("Epoch no: [{}/{}] - Average Loss: {:.5f} - Average PSNR: {:.3f}".format(e,
                                                                                                   epochs,
                                                                                                   float(train_loss/num_of_batches),
                                                                                                   float(total_psnr/num_of_batches)))
                    # #to check if upscaled properly
                    # print("output.shape:", o.shape)

                    # Save (tensorflow variables are only alive within the session, so we should save within the session)
                    save_path = saver.save(sess, self.ckpt_path + "fsrcnn_ckpt")
                except tf.errors.OutOfRangeError:
                    pass

            print("Training finished.")
            train_writer.close()

    def test(self, test_image_path, out, scale):

        # Init
        lr_size = 10
        if(scale == 3):
            lr_size = 7
        elif(scale == 4):
            lr_size = 6
        
        hr_size = lr_size * scale

        # Load image
        np_im = cv2.imread(test_image_path, 3)
        # make it divisible by scale
        #print("np_im.shape:", np_im.shape)
        #np_im = np_im[0:(np_im.shape[0] - (np_im.shape[0] % 2)), 0:(np_im.shape[1] - (np_im.shape[1] % 2)), :]
        #print("np_im.shape:", np_im.shape)
        
        upsampled_np_im = cv2.resize(np_im, (np_im.shape[1]*scale, np_im.shape[0]*scale), interpolation=cv2.INTER_CUBIC)

        # Prepare image for loading into neural network
        np_im_ycc = cv2.cvtColor(np_im, cv2.COLOR_BGR2YCrCb)
        img_ycc = np_im_ycc[:,:,0]
        floatimg_norm = img_ycc.astype(np.float32) / 255.0
        LR_input_ = floatimg_norm.reshape(1, floatimg_norm.shape[0], floatimg_norm.shape[1], 1)
        HR_input_ = upsampled_np_im[:,:,0].reshape(1, upsampled_np_im.shape[0], upsampled_np_im.shape[1], 1)

        # Make LR and HR_cubic windows
        cv2.namedWindow('LR', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('LR', np_im.shape[1], np_im.shape[0])
        cv2.namedWindow('HR bicubic', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('HR bicubic', upsampled_np_im.shape[1], upsampled_np_im.shape[0])

        graph = tf.get_default_graph()
        with graph.as_default():
            with tf.Session(config=self.config) as sess:

                ### Restore checkpoint
                ckpt_name = self.ckpt_path + "fsrcnn_ckpt" + ".meta"
                saver = tf.train.Saver(tf.global_variables())
                saver = tf.train.import_meta_graph(ckpt_name)
                saver.restore(sess, tf.train.latest_checkpoint(self.ckpt_path))
                print("Loaded model for testing.")
                
                print("Testing...")
                # Get prediction
                output = sess.run(out, feed_dict={self.LR_holder: LR_input_, self.HR_holder: HR_input_})
                print("Testing finished.")
               
                # Denormalize and cast to int
                Y = output[0] * 255
                Y = Y.astype(np.uint8)
                
                # Merge with Cr/Cb
                Cr = np.expand_dims(cv2.resize(np_im_ycc[:,:,1], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), axis=2)
                Cb = np.expand_dims(cv2.resize(np_im_ycc[:,:,2], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), axis=2)
                HR_image = (cv2.cvtColor(np.concatenate((Y, Cr, Cb), axis=2), cv2.COLOR_YCrCb2BGR))

                # Show images
                cv2.imshow('LR', np_im)
                cv2.imshow('HR bicubic', upsampled_np_im)
                cv2.imshow('HR nn upscale', HR_image)
                cv2.waitKey(0)