#!/usr/bin/env python


#--------Include modules---------------
from copy import copy
import rospy
from visualization_msgs.msg import Marker
from std_msgs.msg import String
from geometry_msgs.msg import Point
from nav_msgs.msg import OccupancyGrid
import actionlib_msgs.msg
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
from geometry_msgs.msg import PointStamped 
from geometry_msgs.msg import PoseStamped
from nav_msgs.srv import GetPlan
import actionlib
import tf



from time import time
from os import system
from random import random
from numpy import array,concatenate,vstack,delete,floor,ceil
from numpy import linalg as LA
from numpy import all as All
from numpy import inf
from functions import Nearest,Nearest2,Steer,Near,ObstacleFree2,Find,Cost,prepEdges,gridValue
from assigner2_functions import robot,informationGain,discount,pathCost,unvalid
from sklearn.cluster import KMeans
from sklearn.cluster import MeanShift
import numpy as np
from numpy.linalg import norm


from assigner2_functions import robot

# Subscribers' callbacks------------------------------
mapData=OccupancyGrid()
frontiers=[]
global1=OccupancyGrid()
global2=OccupancyGrid()
global3=OccupancyGrid()

def callBack(data):
	global frontiers,min_distance
	x=[array([data.x,data.y])]
	if len(frontiers)>0:
		frontiers=vstack((frontiers,x))
	else:
		frontiers=x
    

def mapCallBack(data):
    global mapData
    mapData=data

def globalMap1(data):
    global global1
    global1=data
    
def globalMap2(data):
    global global2
    global2=data

def globalMap3(data):
    global global3
    global3=data
    
# Node----------------------------------------------

def node():
	k=0
	global frontiers,mapData,global1,global2,global3
	rospy.init_node('assigner', anonymous=False)
	
	# fetching all parameters
	map_topic= rospy.get_param('~map_topic','/map_merge/map')
	info_radius= rospy.get_param('~info_radius',1.0)					#this can be smaller than the laser scanner range, >> smaller >>less computation time>> too small is not good, info gain won't be accurate
	info_multiplier=rospy.get_param('~info_multiplier',3.0)		
	hysteresis_radius=rospy.get_param('~hysteresis_radius',3.0)			#at least as much as the laser scanner range
	hysteresis_gain=rospy.get_param('~hysteresis_gain',2.0)				#bigger than 1 (biase robot to continue exploring current region
	goals_topic= rospy.get_param('~goals_topic','/exploration_goals')	
	n_robots = rospy.get_param('~n_robots',3)
	global_frame=rospy.get_param('~global_frame','/robot_1/map')

	rate = rospy.Rate(100)
#-------------------------------------------
	rospy.Subscriber(map_topic, OccupancyGrid, mapCallBack)
	rospy.Subscriber('/robot_1/move_base_node/global_costmap/costmap', OccupancyGrid, globalMap1)
	rospy.Subscriber('/robot_2/move_base_node/global_costmap/costmap', OccupancyGrid, globalMap2)
	rospy.Subscriber('/robot_3/move_base_node/global_costmap/costmap', OccupancyGrid, globalMap3)
	rospy.Subscriber(goals_topic, Point, callBack)
	pub = rospy.Publisher('frontiers', Marker, queue_size=10)
	pub2 = rospy.Publisher('centroids', Marker, queue_size=10)
#---------------------------------------------------------------------------------------------------------------

    	
	while len(frontiers)<1:
		pass	




	points=Marker()
	points_clust=Marker()
#Set the frame ID and timestamp.  See the TF tutorials for information on these.
	points.header.frame_id= "/robot_1/map"
	points.header.stamp= rospy.Time.now()

	points.ns= "markers2"
	points.id = 0
	
	points.type = Marker.POINTS
	
#Set the marker action for latched frontiers.  Options are ADD, DELETE, and new in ROS Indigo: 3 (DELETEALL)
	points.action = Marker.ADD;

	points.pose.orientation.w = 1.0

	points.scale.x=0.2
	points.scale.y=0.2 

	points.color.r = 255.0/255.0
	points.color.g = 255.0/255.0
	points.color.b = 0.0/255.0

	points.color.a=1;
	points.lifetime = rospy.Duration();

	p=Point()


	p.z = 0;

	pp=[]
	pl=[]
    	
    	
    	
    	
    	
	points_clust.header.frame_id= "/robot_1/map"
	points_clust.header.stamp= rospy.Time.now()

	points_clust.ns= "markers3"
	points_clust.id = 4

	points_clust.type = Marker.POINTS

#Set the marker action for centroids.  Options are ADD, DELETE, and new in ROS Indigo: 3 (DELETEALL)
	points_clust.action = Marker.ADD;

	points_clust.pose.orientation.w = 1.0;

	points_clust.scale.x=0.2;
	points_clust.scale.y=0.2; 

	points_clust.color.r = 0.0/255.0
	points_clust.color.g = 255.0/255.0
	points_clust.color.b = 0.0/255.0

	points_clust.color.a=1;
	points_clust.lifetime = rospy.Duration();

	robots=[]
	for i in range(0,n_robots):
		robots.append(robot('/robot_'+str(i+1)))
	for i in range(0,n_robots):
		robots[i].sendGoal(robots[i].getPosition())
#-------------------------------------------------------------------------
#---------------------     Main   Loop     -------------------------------
#-------------------------------------------------------------------------

	while not rospy.is_shutdown():

#-------------------------------------------------------------------------	
#clearing old frontiers         
		z=0
		while z<len(frontiers):
			if gridValue(mapData,frontiers[z])!=-1:
				frontiers=delete(frontiers, (z), axis=0)
				z=z-1
			z+=1
#-------------------------------------------------------------------------
#Clustering frontier points
		centroids=[]
		if len(frontiers)>1:
			ms = MeanShift(bandwidth=2.0)   
			ms.fit(frontiers)
			centroids= ms.cluster_centers_	 #centroids array is the centers of each cluster

		#if there is only one frontier no need for clustering, i.e. centroids=frontiers
		if len(frontiers)==1:
			centroids=frontiers		
#-------------------------------------------------------------------------			
#Get information gain for each frontier point
		infoGain=[]
		for ip in range(0,len(centroids)):
			infoGain.append(informationGain(mapData,[centroids[ip][0],centroids[ip][1]],info_radius))
#-------------------------------------------------------------------------		
		print 'infoGain before discount: ',infoGain
#-------------------------------------------------------------------------			
#get number of available/busy robots
		na=[] #available robots
		nb=[] #busy robots
		for i in range(0,n_robots):
			if (robots[i].getState()==1):
				nb.append(i)
			else:
				na.append(i)
#------------------------------------------------------------------------- 
		print 'available robots: ',na			
#------------------------------------------------------------------------- 
#get dicount and update informationGain
		for i in nb:
			infoGain=discount(mapData,robots[i].assigned_point,centroids,infoGain,info_radius)

#-------------------------------------------------------------------------		
		print 'infoGain after discount: ',infoGain
#-------------------------------------------------------------------------            
		revenue_record=[]
		centroid_record=[]
		id_record=[]
		
		for ir in na:
			for ip in range(0,len(centroids)):
				cost=norm(robots[ir].getPosition()-centroids[ip])		
				#cost=pathCost(robots[ir].makePlan(robots[ir].getPosition(),centroids[ip]))  #old cost calculation, slow, takes around 0.2 sec for each iteration
				if 	gridValue(global1,centroids[ip])>50 or gridValue(global2,centroids[ip])>50 or gridValue(global3,centroids[ip])>50:
					cost=inf
				information_gain=infoGain[ip]
				if (norm(robots[ir].getPosition()-centroids[ip])<=hysteresis_radius):
					information_gain*=hysteresis_gain
				revenue=information_gain*info_multiplier-cost
				revenue_record.append(revenue)
				centroid_record.append(centroids[ip])
				id_record.append(ir)

#-------------------------------------------------------------------------		
		print 'revenue_record: ',revenue_record,'\n'
		print 'centroid_record: ',centroid_record,'\n'
#-------------------------------------------------------------------------	
		if ((len(centroids)>2 or k==1) and len(id_record)>0):
			k=1
			winner_id=revenue_record.index(max(revenue_record))
			robots[id_record[winner_id]].sendGoal(centroid_record[winner_id])
			print 'robot_',id_record[winner_id], 'assigned to ',centroid_record[winner_id]
			rospy.sleep(1.0)

#------------------------------------------------------------------------- 
#cancel mission if the point is no longer unknown
		for i in nb:
			if gridValue(mapData,robots[i].assigned_point)!=-1:
				robots[i].cancelGoal()
				print 'aborting for robot_',i,'        point: ',robots[i].assigned_point
				
				print '____________________________________'
				print '\n \n'
			
#-------------------------------------------------------------------------
#Plotting
		pp=[]	
		for q in range(0,len(frontiers)):
			p.x=frontiers[q][0]
			p.y=frontiers[q][1]
			pp.append(copy(p))
		points.points=pp
	
	
		pp=[]	
		for q in range(0,len(centroids)):
			p.x=centroids[q][0]
			p.y=centroids[q][1]
			pp.append(copy(p))
		points_clust.points=pp
			
		pub.publish(points)
		pub2.publish(points_clust) 
		rate.sleep()



#-------------------------------------------------------------------------

if __name__ == '__main__':
    try:
        node()
    except rospy.ROSInterruptException:
        pass
 
 
 
 
