wget http://ftp.gnu.org/pub/gnu/gperf/gperf-3.3.tar.gz
tar -xzvf gperf-3.3.tar.gz
./configure --prefix=/public/home/zhangxin/external-libraries/gperf-3.3
make -j6
make install