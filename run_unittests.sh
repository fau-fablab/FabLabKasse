#!/bin/sh
# run all unittest cases in *_unittest.py files inside FabLabKasse
python -m unittest discover -p '*_unittest.py' FabLabKasse/
