#!/bin/sh

if [ ! -d "venv" ]; then 
    python -m venv venv
    venv/bin/pip install -e ..
fi
venv/bin/pip install -r requirements.txt
texttest -d .

