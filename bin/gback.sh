#!/bin/bash
command=$@
echo "command:${command}"
git checkout HEAD ${command}
