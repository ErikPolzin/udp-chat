#!/bin/bash

if [[ "$1" != "udpchat://" ]]; then 
    udpchat_gui $1
else 
    udpchat_gui
fi