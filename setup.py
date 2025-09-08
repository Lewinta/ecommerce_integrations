from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in ecommerce_integrations/__init__.py
from ecommerce_integrations import __version__ as version

setup(
	name="ecommerce_integrations",
	version=version,
	description="Custom Version for Ecommerce Integrations",
	author="Lewin Villar",
	author_email="lewin@tzcode.tech",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires,
)