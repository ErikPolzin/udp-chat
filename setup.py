from setuptools import setup, find_packages
import pathlib


HERE = pathlib.Path(__file__).parent
README = (HERE / "README.md").read_text()


setup(name='udp_chat',
    version='0.1.2',
    description='UDP-based chat application',
    long_description=README,
    long_description_content_type="text/markdown",
    url='https://github.com/ErikPolzin/udp-chat',
    author='Ohio Imevbore, Luke Slater, Erik Polzin',
    license='MIT',
    packages=find_packages(include=['udp_chat', 'udp_chat.*']),
    zip_safe=False,
    install_requires=[
        'PyQt5>=5.14.1',
        'qasync>=0.23.0',
        'pygments'
    ],
    entry_points={
        'console_scripts': [
            'udpchat_server=udp_chat.server:main',
            'udpchat_cli=udp_chat.client:main',
            'udpchat_gui=udp_chat.gui_client:main',
        ]
    })