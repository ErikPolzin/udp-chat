from setuptools import setup, find_packages

setup(name='udp_chat',
    version='0.1',
    description='UDP-based chat application',
    url='https://github.com/ErikPolzin/udp-chat',
    author='Ohio Imevbore, Luke Slater, Erik Polzin',
    license='MIT',
    packages=find_packages(include=['udp_chat', 'udp_chat.*']),
    zip_safe=False,
    install_requires=[
        'PyQt5>=5.14.1',
        'qasync>=0.23.0'
    ],
    entry_points={
        'console_scripts': [
            'udpchat_server=udp_chat.server:main',
            'udpchat_cli=udp_chat.client:main',
            'udpchat_gui=udp_chat.gui_client:main',
        ]
    })