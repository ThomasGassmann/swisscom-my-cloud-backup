from setuptools import setup


with open('requirements.txt', 'r') as f:
    install_reqs = [
        s for s in [
            line.strip(' \n') for line in f
        ] if not s.startswith('#') and s != ''
    ]


setup(
    name='mycloud-cli',
    version='1.2.0',
    license='MIT',
    author='Thomas Gassmann',
    author_email='thomas.gassmann@hotmail.com',
    url='https://github.com/ThomasGassmann/mycloud-cli',
    py_modules=['mycloud'],
    install_requires=install_reqs,
    entry_points={
        'console_scripts': {'console_scripts': ['mycloud=mycloud:main']}
    }
)