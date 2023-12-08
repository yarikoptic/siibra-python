#! /bin/bash

# Populate datamodels based on jsonschema generated by siibra-explorer
# require 
# pip install datamodel-code-generator
# which is not a part of requirements
# Usage:
# ./generate_dataclass.sh \ 
#   $PATH_SIIBRA_EXPLORER_ROOT_DIR \
#   $PATH_TO_SIIBRA_PYTHON_EXPLORERAPI_DIR
#
# $$PATH_TO_SIIBRA_PYTHON_EXPLORERAPI_DIR is usually ~/siibra/explorer/api

if [[ -z "$1" ]]
then
    echo "Path to siibra-explorer is required to populate"
    exit 1
fi

if [[ -z "$2" ]]
then
    echo "Output path is required"
    exit 1
fi

for f in $(find $1/src/api -type f -name '*.json')
do
    echo "Processing $f"
    dst_file=${f#$1/src/api/}
    dst_file=${dst_file%.json}
    dst_name=$(basename $dst_file)
    dst_dir=$(dirname $dst_file)

    subdir="other"
    if [[ $dst_name == *"request"* ]]
    then
        subdir="request"
    fi
    if [[ $dst_name == *"response"* ]]
    then
        subdir="response"
    fi
    
    dst_name=${dst_name%__request}
    dst_name=${dst_name%__response}
    dst_name=${dst_name%__fromSxplr}
    dst_name=${dst_name%__toSxplr}
    dst_name=${dst_name#sxplr.}
    dst_name=${dst_name#on.}

    dst=$2/$dst_dir/$dst_name/$subdir

    mkdir -p $dst
    datamodel-codegen --input $f \
        --input-file-type jsonschema \
        --output-model-type dataclasses.dataclass \
        --output $dst/__init__.py
    
    echo "============================="
done

datamodel-codegen --input $1/src/api/request/sxplr.navigateTo__toSxplr__request.json \
    --input-file-type jsonschema \
    --output-model-type dataclasses.dataclass \
    --output $2/request/navigateTo/request
