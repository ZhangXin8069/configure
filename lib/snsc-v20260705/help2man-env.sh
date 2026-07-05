wget https://mirror.twds.com.tw/gnu/help2man/help2man-1.48.3.tar.xz
tar -xvf help2man-1.48.3.tar.xz
cd help2man-1.48.3
./configure --prefix=/public/home/zhangxin/external-libraries/help2man-1.48.3
make -j6
make install