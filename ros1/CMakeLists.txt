cmake_minimum_required(VERSION 3.0.2)
project(bsactuator_ros)

find_package(catkin REQUIRED COMPONENTS
  rospy
)

catkin_python_setup()

catkin_package(
  CATKIN_DEPENDS rospy
)

catkin_install_python(PROGRAMS 
  nodes/bsactuator_ros
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

