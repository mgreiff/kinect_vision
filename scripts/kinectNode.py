#!/usr/bin/env python
import rospy
import ros_numpy
import math
from math import ceil
import numpy as np
import matplotlib.pyplot as plt
import os,sys,inspect
import time
from scipy.linalg import svd, norm, solve, inv
from math import acos, pi
from sensor_msgs.msg import Image
from rospy.numpy_msg import numpy_msg
from geometry_msgs.msg import Point
from std_msgs.msg import String
from crazy_ros.msg import NumpyArrayFloat64
from json import load

class KinectNode(object):
    """
    Defines the class for reading and filtering the kinect data. When run,
    this class reads parameters from the configuration.cfg file.
    When initializing the node, the background is calibrated automatically
    with one of two methods (SVD or polyfit) this can be redone by publishing
    the string 'recalibrate' to the topic /*** which the sets self.cal_frames
    to 0. Similarily, the gorund and the angle can be re-calibrated by
    calling calibrate_angle_SVD() or calibrate_angle().
   
    When in an idle state, the note continuously takes data from the openni 
    driver, preocesses it by means of an augmented Kalman filter and
    publishes an estimated position and velocity of the object to 
    the topic /kinect/pos and /kinect/vel. The process uses the signal module
    to terminate nicely on ctrl+C.
    """
    def __init__(self):
        self.background = None # Initial background is set to none
        self.angle = None      # The calibration angle of 
        self.cal_frame = 0     # Counter used in background calibration
        self.scatter = None    # Figure handle for scatter plot 
        self.ims = None        # Figure handle for plotting
        self.useKalman = True  # Compute and publish kalman estimate
        self.plot = False      # Plot the depth data in real time
        if self.plot:
            plt.ion()

        # Camera centers and focal lengths (see /camera/depth/camera_info)
        self.f_x = 570.34
        self.f_y = 570.34
        self.c_x = 314.5
        self.c_y = 235.5

        # Loads configuration parameters
        for arg in rospy.myargv(argv=sys.argv):
            filename = os.path.basename(arg)
            if len(filename) > 3:
                if filename[-4:len(filename)] == '.cfg':
                    if filename == 'default.cfg':
                        print '\n(@ kinectNode) Loading default configurations...\n'
                    else:
                        print '\n(@ kinectNode) Loading %s...\n' % filename
                    with open(arg) as configfile:
                        param = load(configfile)
                    configfile.close()
        try:
            self.Q = np.diag(param['kinect']['Q'])
            self.R = np.diag(param['kinect']['R'])
            self.P = np.diag(param['kinect']['P0'])
            self.xhat = np.array(param['kinect']['x0'])
            self.Ts = param['kinect']['kalman_timestep']
            self.kalmanLimit = param['kinect']['kalman_epsilon']
            self.backgroundLimit = param['kinect']['background_epsilon']
            self.calibrationLimit = param['kinect']['calibration_epsilon']
        except:
            raise ValueError('ERROR. Could not load configuration parameters in %s' % (str(self)))

        # 3D double integrator discrete time dynamics
        self.A = np.eye(6) + np.diag(self.Ts*np.ones((1,3))[0],3)
        self.C = np.zeros((3,6))
        self.C[0,0] = 1.
        self.C[1,1] = 1.   
        self.C[2,2] = 1.

        # Sets up publishers and subscribers
        self.disparity_sub = rospy.Subscriber('/camera/depth/image_rect', Image, self.handle_disparity_image)
        self.status_sub = rospy.Subscriber('/kinect/in', String, self.handle_status)        # Interacting with the node
        self.status_pub = rospy.Publisher('/kinect/out', String, queue_size = 10)           # Interacting with the node
        self.pos_pub = rospy.Publisher('/kinect/position', Point, queue_size = 10)          # Publishes positions
        self.vel_pub = rospy.Publisher('/kinect/velocity', Point, queue_size = 10)          # Publishes velocities
        self.pos_raw_pub = rospy.Publisher('/kinect/position_raw', Point, queue_size = 10)  # Publishes raw positions

    def handle_status(self, msg):
        """
        Callback for the /kinect/in subscriber. The subscbiber takes
        a string argument, set to
            * recalibrate - Initializes calibration of both
                background and angle on the next cycle.
            * background - Visualises the background image in
                the plot handle self.ims.
            * plot - Visualises the filtered point 
                the plot handle self.ims.
        """
        if msg.data == 'recalibrate':
            self.background = None
            self.cal_frame = 0
            self.angle = None
        elif msg.data == 'background':
            self.plot = False
            self.ims.set_data(self.background)
        elif msg.data == 'plot':
            self.plot = True
        else:
            print 'The argument "%s" is not yet supported.' % msg.data

    def handle_disparity_image(self, image):
        """
        Handles the kinect data, calling the calibration functions, coordinate
        transformations, and filtering the data using a discrete Kalman filter
        with a 3D double integrator model.
        """
        np_image = ros_numpy.numpify(image)
        np_image_rel = np_image
        
        if self.cal_frame < self.calibrationLimit:
            # Calibrates background
            if not self.cal_frame:
                print '\n(@ kinectNode) Calibrating background...'
            self.print_progress(self.cal_frame, self.calibrationLimit-1, "(@ kinectNode) Progress:",'Complete')

            if self.background is None:
                self.background = np.zeros(np_image.shape)
            self.background += np_image / 30.0
            self.cal_frame += 1
            mask = np.isnan(self.background)
            self.background[mask] = np.interp(np.flatnonzero(mask), np.flatnonzero(~mask), self.background[~mask])
        else:
            # Calibrates angle
            np_image_rel = self.background - np_image
            if self.angle is None:
                print '(@ kinectNode) Calibrating angle...'

                singval = self.calibrate_angle_SVD()
                print '(@ kinectNode) SVD: %f [deg], singular values %s' % (180/pi * self.angle, str(singval))

                best_r = self.calibrate_angle_polyfit()
                print '(@ kinectNode) Polyfit: %f [deg], residual r = %f' % (180/pi * self.angle, best_r[0])
                print '(@ kinectNode) Calibration complete!\n'

                self.status_pub.publish('True')

            # Runs in regular mode, publishing the position in the global
            # coordinate system
            i, j = np.mean(np.where(np_image_rel>(np.nanmax(np_image_rel) - self.backgroundLimit)), axis=1)

            if self.plot:
                if self.ims is None:
                    self.ims = plt.figure(1)
                    self.ims = plt.imshow(np_image_rel, vmin = 0, vmax = 5)
                    plt.colorbar()
                else:
                    self.ims.set_data(np_image_rel)
                    if self.scatter is not None:
                        self.scatter.remove()
                    self.scatter = plt.scatter([j], [i], color='red')
                plt.draw()
                plt.pause(0.01)

            x, y, z = self.point_from_ij(i, j, np_image)

            p_raw = Point(x=x, y=y, z=z)
            self.pos_raw_pub.publish(p_raw)

            # Kalman filter update - computes, updates and prints the position
            # and covariance
            if self.useKalman:
                zk = np.array([x,y,z])
                # Treats the case when a measurement is missed
                if np.isnan(zk).any() or norm(zk - self.xhat[0:3]) > self.kalmanLimit*norm(np.diag(self.P)[0:3]):
                    zk = None
                self.xhat, self.P = self.discrete_KF_update(self.xhat, [], zk, self.A, [], self.C, self.P, self.Q, self.R)
                p = Point(x=self.xhat[0], y=self.xhat[1], z=self.xhat[2])
                v = Point(x=self.xhat[3], y=self.xhat[4], z=self.xhat[5])
                self.pos_pub.publish(p)
                self.vel_pub.publish(v)

    def point_from_ij(self, i, j, np_image, rotate = True):
        """
        Maps the coordinate at index (i,j) in the np_image to the camera
        coordinate system if rotate = False, or into the global coordinate
        system if rotate = True and the attirbute self.angle != None. 
        """
        x_c = np.round(j)
        y_c = np.round(i)
        
        z = np_image[y_c, x_c]
        x = (x_c - self.c_x)*z/self.f_x
        y = -(y_c - self.c_y)*z/self.f_y

        if self.angle is not None and rotate:
            s = math.sin(self.angle)
            c = math.cos(self.angle)
            y, z = c*y + s*z, -s*y + c*z
        return x, y, z

    def calibrate_angle_polyfit(self):
        """
        Approximates a 2D-line to the set of points and computes the angle.
        See the documentations  for the mathematics involved. Uses measured
        background (self.background) and the numpy polyfit function updating
        the self.angle attribute with a new calibrated angle.
        """

        def compute_angle(self, o):
            """
            Maps points in the background matrix into the camera coordinate
            system (global coordinate system without rotation) and fits 
            a 2D-line through a set of points in the y-z plane, for the
            y-indices range(o,n). The residual, r, and the angle between
            the fitted line and the z-axis is returned
            """
            j, n = 320, 100
            i_l = range(o, o + n)
            y_l, z_l = np.zeros(n), np.zeros(n)
            for ind, i in enumerate(i_l):
                x, y, z = self.point_from_ij(i, j, self.background, rotate = False)
                y_l[ind], z_l[ind] = y, z
            p, r, _, _, _ = np.polyfit(y_l, z_l, 1, full = True)
            return np.arctan(p[0]), r
        
        self.angle = None
        for i in range(0, 400, 50):
            angle, r = compute_angle(self, i)
            if self.angle is None or r < best_r:
                best_r, self.angle, best_i = r, angle, i

                # Found roof
                if self.angle < -0.2:
                    self.angle += math.pi/2
        return best_r

    def calibrate_angle_SVD(self):
        """
        Approximates a 3D-plane to the set of points and computes the angle.
        See the documentation for the mathematics involved. Uses measured
        background (self.background) and the scipy svd function updating
        updating the self.angle attribute with a new calibrated angle.
        """

        # Samples background matrix, finds S
        pointsX = 10
        pointsY = 20
        nX, nY = self.background.shape
        
        indX = [ceil(ii * nX / pointsX) for ii in range(pointsX)]
        indY = [ceil(ii * nY / pointsY) for ii in range(pointsY)]
        x = np.zeros(pointsX * pointsY)
        y = np.zeros(pointsX * pointsY)
        z = np.zeros(pointsX * pointsY)
        count = 0
        for ii in indX:
            for jj in indY:
                z[count] = self.background[ii,jj]
                x[count] = (ii - self.c_x) * z[count] / self.f_x
                y[count] = -(jj - self.c_y) * z[count] / self.f_y
                count += 1

        # Sets up P and computes 3D-plane normal and inclination angle
        P = np.array([sum(x),sum(y),sum(z)])/len(z);
        [U,S,V] = svd(np.transpose(np.array([x-P[0],y-P[1],z-P[2]])));
        N = -1./V[2,2]*V[2,:]
        XZnormal = np.array([[N[0]],[N[2]]])
        self.angle = acos(N[0]/norm(XZnormal)) - pi/2
        return np.round(S,2)

    def discrete_KF_update(self, x, u, z, A, B, C, P, Q, R):
        """
        Makes a discrete kalman update and returns the new state
        estimation and covariance matrix. Can handle empy control
        signals and empty B. Currently no warnings are issued if
        used improperly, which should be fixed in future iterations.
        If z is set to None, the update step is ignored and only prediction
        is used.
       
        N<=M and 0<K<=M are integers.
        
        Args:
           x - np.array of shape (M,1). State estimate at t = h*(k-1)
           u - np.array of shape (N,1), emty list or None. If applicable, control
               signals at t = h*(k-1)
           z - np.array of shape (K,1). Measurements at t = h*k.
           A - np.array of shape (M,M). System matrix.
           B - np.array of shape (M,N), emty list or None. Control signal matrix.
           C - np.array of shape (K,M). Measurement matrix.
           P - np.array of shape (M,M). Covariance at the previous update.
           Q - np.array of shape (M,M). Estimated covariance matrix of model
               noise.
           R - np.array of shape (K,K). Estimated covariance matrix of
               measurement noise.
       
        Returns:
           xhat - New estimate at t = h*k
           Pnew - New covariance matrix at t = h*k
        """
        
        # Kalman prediction
        if B == [] or u == []:
            xf = np.transpose(np.dot(A,x))
        else:
            xf = np.transpose(np.dot(A,x)) + np.transpose(np.dot(B,u))
        Pf = np.dot(np.dot(A,P),np.transpose(A)) + Q
        
        # Kalman update
        if z is not None:
            Knum =  np.dot(Pf,np.transpose(C))
            Kden = np.dot(C,np.dot(Pf,np.transpose(C))) + R
            K = np.dot(Knum,inv(Kden))
            xhat = xf + np.dot(K, (z - np.dot(C,xf)))
            Pnew = np.dot((np.eye(Q.shape[0]) - np.dot(K,C)), Pf)
        else:
            xhat = xf
            Pnew = Pf
        return xhat, Pnew
    
    def __str__(self):
        return 'kinect node'

    def print_progress (self,iteration, total, prefix, suffix):
        """
        Prints progress bar in terminal window
        ARGS:
           iteration - positive integer. The current iteration.
           total - positive integer > iteration. The total number of iterations before completion.
           prefix - string. Empty by default, specifies text before the progress bar.
           suffix - string. Empty by default, specifies text after the progress bar.
           decimals - positive integer. number of decimals in the percentage calculation.
           barLength - positive, non-zero integer. Set to 30 # by default.
        """
        decimals = 2
        barLength = 30
        filledLength = int(round(barLength * iteration / float(total)))
        percents = round(100.00 * (iteration / float(total)), decimals)
        bar = '#' * filledLength + '-' * (barLength - filledLength)
        sys.stdout.write('%s [%s] %s%s %s\r' % (prefix, bar, percents, '%', suffix)),
        sys.stdout.flush()
        if iteration == total:
            print("\n")

if __name__ == '__main__':
    rospy.init_node('kinectNode')
    kin = KinectNode()
    rospy.spin()
