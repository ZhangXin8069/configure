wget -c https://ftp.gnu.org/gnu/texinfo/texinfo-6.6.tar.gz
tar -xzvf texinfo-6.6.tar.gz
cd texinfo-6.6/
./configure --prefix=/public/home/zhangxin/external-libraries/texinfo-6.6
make -j6
make install