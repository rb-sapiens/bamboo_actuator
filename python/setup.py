from setuptools import find_packages, setup

setup(
    name="bamboo_actuator",
    version="0.3.0",
    description="Serial client for BambooActuator",
    packages=find_packages(),
    install_requires=["pyserial>=3.0"],
    python_requires=">=3.8",
)
