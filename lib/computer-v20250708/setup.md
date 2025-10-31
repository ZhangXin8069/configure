0. docker login
1. docker commit v20250216  computer-v20250708
2. docker run -itd --gpus all --name computer-v20250708 -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NVIDIA_VISIBLE_DEVICES=all -v /d/docker:/root/windows zhangxin8069/computer-v20250708
3. docker commit computer-v20250708  zhangxin8069/computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17
4. docker push  zhangxin8069/computer-v20250708:ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17
> or:
0. docker ps -a
1. docker export a64e923a81b1 > computer-v20250708_ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17.tar
2. update 'computer-v20250708_ubuntu-22.04_gcc-11.4.0_python-3.10.12_cuda-12.4.0_quda-develop-sm80_pyqcu-stab17.tar' to aliyundrive.
