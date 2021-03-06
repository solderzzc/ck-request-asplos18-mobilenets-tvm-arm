#! /bin/bash

#
# Installation script for Caffe.
#
# See CK LICENSE for licensing details.
# See CK COPYRIGHT for copyright details.
#
# Developer(s):
# - Grigori Fursin, 2015;
# - Anton Lokhmotov, 2016.
#

# PACKAGE_DIR
# INSTALL_DIR

######################################################################################
# Check if has --system option
${CK_ENV_COMPILER_PYTHON_FILE} -m pip install --help > tmp-pip-help.tmp
if grep -q "\-\-system" tmp-pip-help.tmp ; then
 SYS=" --system"
fi
rm -f tmp-pip-help.tmp

######################################################################################
echo "Downloading and installing deps ..."
echo ""

EXTRA_PYTHON_SITE=${INSTALL_DIR}/src/python

${CK_ENV_COMPILER_PYTHON_FILE} -m pip install --ignore-installed decorator wget -t ${EXTRA_PYTHON_SITE}  ${SYS}
if [ "${?}" != "0" ] ; then
  echo "Error: installation failed!"
  exit 1
fi

echo "**************************************************************"
echo "Preparing vars for TVM ..."

# Check extra stuff
EXTRA_FLAGS=""

cd ${INSTALL_DIR}/src
pwd 
make -j ${CK_HOST_CPU_NUMBER_OF_PROCESSORS} \
      USE_OPENCL=${USE_OPENCL}\
      LLVM_CONFIG=${CK_LLVM_CONFIG} \

if [ "${?}" != "0" ] ; then
  echo "Error: make failed!"
  exit 1
fi

echo "**************************************************************"
echo "Preparing vars for NVVM ..."

cd ${INSTALL_DIR}/src/nnvm

make; 
if [ "${?}" != "0" ] ; then
  echo "Error: cmake failed!"
  exit 1
fi
#export PACKAGE_BUILD_TYPE=skip

return 0
