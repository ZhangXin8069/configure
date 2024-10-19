pushd ~/
# wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
./Miniconda3-latest-Linux-x86_64.sh
popd
######
conda create --no-default-packages --name qcu 
conda activate qcu
conda install gcc=11.4 -c conda-forge
conda install python=3.10.12
conda install cuda=12.4.1