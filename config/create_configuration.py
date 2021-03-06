#!/usr/bin/env python
import json

param = {
    'kinect':{
        'Q': [1.,1.,1.,1.,1.,1.],               # Diagonal of the Q matrix
        'R': [.5,.5,.5],                        # Diagonal of the R matrix
        'P0': [10.,10.,10.,10.,10.,10.],        # Diagonal of the initial covariance matrix
        'x0': [0.,0.,0.,0.,0.,0.],              # Initial condition for state estimation
        'kalman_timestep': 0.0333,              # Roughly the time between data updates from the openni
        'kalman_epsilon': 0.15,                 # The limit for determining prediction quality
        'background_epsilon': 0.1,              # The bound for distinguishing background noise
        'calibration_epsilon': 30
    }
}

with open('kinect_config.cfg', 'w') as cnffile:
    json.dump(param, cnffile, separators=(',', ':'),sort_keys=True, indent=4)
