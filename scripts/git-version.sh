#!/bin/bash
cat <<EOF > git-version.h
#define GIT_VERSION 0x$(git rev-parse --short HEAD)
EOF
