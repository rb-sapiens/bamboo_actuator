import os

from setuptools import find_packages, setup

package_name = "bamboo_actuator_ros2"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("lib", package_name), [os.path.join("scripts", "bamboo_actuator_node")]),
    ],
    install_requires=["setuptools", "bamboo_actuator>=0.3.0"],
    zip_safe=False,
    maintainer="Shun Nagao",
    maintainer_email="nagao@rb-sapiens.com",
    description="Robosapiens BSA application (Unitree Go2 ROS 2, Python)",
    license="Apache-2.0",
)
