# kinect_vision
ROS package for locating small objects in space. The package combines the
openni kinect driver with the ros_numpy package and uses a simple tripple 
integrator model with a Kalman filter and some additional tricks to estimate
the position and velocities for the object. The software was used to 
successfully fly the very small Crazyflie 2.0 quadcopter [[1]] with state
feedback from the kinect, and is easily integratable into any low budget
robotics project. A brief demonstration of performance and the mathematics
involved can be found in the
[/documentation](../blob/master/documentation) directory.

### Features
* Automatic calibration and recalibration of the background and camera angle,
  done using one of two methods. The first uses polyfit and other utilises the
  singular value decomposition for plane 3D-fitting.
* Publishes the raw position of the object optionally the Kalman filtered
  position and velocities of the object only using prediction when a bad
  measurement is registered. Data is published at a rate of 30 Hz.
* Configuration files which can be used to save and load system wide settings.
* Optional live plotting of background image and estimated position.

### Dependencies and requirements
* The openni_launch driver [[2]].
* The numpy_ros package [[3]].
* Ubuntu 14.04 Trusty [[4]] with a ROS Indigo installation [[5]]*.
* A Microsoft Kinect or a  PrimeSense PSDK oran ASUS Xtion Pro and Pro Live.

*The project could potentially be run with with other versions of Ubuntu and
other ROS distros supported in the openni_launch package, but this has yet to
be verified.

### Installation
Simply follow the installation instructions for installing ROS indigo and
follow the tutorial to set up the catkin workspace [[5]]. Next, clone the
repositories with the openni_launch (or alternatively openni2_launch) and
the numpy_ros package and place the packages in the ~/catkin_ws/src/
dir3ctory. Clone the kinect_vision repo and place the entire project in
~/catkin_ws/src/. Finally, cd to ~/catkin_ws and run

    `$ catkin_init`

When connecting the camera, the entire project is launched by the command 

    `$ roslaunch kinect_vision kinect.launch`

### Useful notes
If the openni driver unable to run, two common reasons are that (1) the global
default file is configured wrong or (2) the camera is incompatible with the
openni driver, in which case the openni2 package can be tried [[6]].

The first problem can be usually solved by running

    `$ sudo nano /etc/openni/GlobalDefaults.ini`

and then changing the settings of the variable UsbInterface=X, such that
UsbInterface=2. Some have reported this variable being set to X=0 by default,
and others have had it commented out (then written ;UsbInterface=X).

[1]: https://www.bitcraze.io/crazyflie-2/
[2]: http://wiki.ros.org/openni_launch
[3]: http://wiki.ros.org/ros_numpy
[4]: http://releases.ubuntu.com/14.04/
[5]: http://wiki.ros.org/indigo/Installation/Ubuntu
[6]: http://wiki.ros.org/openni2_launch
