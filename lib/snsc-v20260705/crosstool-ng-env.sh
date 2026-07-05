wget http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-1.26.0.tar.xz
tar -xvf crosstool-ng-1.22.0.tar.xz
cd crosstool-ng-1.26.0/
./configure --prefix=/public/home/zhangxin/external-libraries/crosstool-ng-1.26.0
make -j6
make install