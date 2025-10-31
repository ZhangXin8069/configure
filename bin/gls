#!/bin/bash
path=$@
echo "path:${path}"
echo "git ls-files ${path}| xargs cat | wc -l"
git ls-files ${path} | xargs cat | wc -l
