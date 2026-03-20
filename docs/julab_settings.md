# julab
**zhangxin's&nbsp;jupyter settings**
**************
## change sources
refer to [this](https://github.com/ZhangXin8069/Install-OpenMC-in-Windows-wsl2-and-change-sources-for-Chinese-users)

## install jupyter
```
# pip
pip install jupyterlab

# or 
# conda
conda install -c conda-forge jupyterlab
```
**********
## install extension
```
pip install jupyterlab-language-pack-zh-CN
pip install jupyterlab-github
pip install jupyterlab_latex
pip install ipympl
pip install jupyterlab-drawio
pip install 'jupyterlab>=3.0.0,<4.0.0a0' jupyterlab-lsp
pip install lckr-jupyterlab-variableinspector
```
refer to [this](https://zhuanlan.zhihu.com/p/101070029)
```
pip install jupyterlab_execute_time
pip install plotly==5.14.0
pip install jupyterlab-system-monitor 
```
refer to [this](https://cloud.tencent.com/developer/article/1971947)
```
pip install magic-markdown
pip install ipython-sql
pip install jupyter_spaces
pip install blackcellmagic
pip install watermark
pip install py-heat-magic
```
```
%load_ext magic_markdown
%load_ext sql
%load_ext jupyter_spaces
%load_ext blackcellmagic
%load_ext watermark
%load_ext heat
```
```
%%mmd
%sql
%%space <test>
%remove_space <test>
%%black
%watermark
%%heat
```
refer to [this](https://blog.csdn.net/weixin_40787712/article/details/119306237)
## install cling(c++ jupyter)
```
wget https://root.cern.ch/download/cling/cling_***.tar.bz2
tar -xjvf cling_***.tar.bz2
```
```
export PATH=/cling-install-prefix/bin:$PATH
cd /cling-install-prefix/share/cling/Jupyter/kernel

pip install -e .
# or: pip3 install -e .

# register the kernelspec for C++17/C++1z/C++14/C++11:
# the user can install whichever kernel(s) they
# wish:
jupyter-kernelspec install --user cling-cpp17
jupyter-kernelspec install --user cling-cpp1z
jupyter-kernelspec install --user cling-cpp14
jupyter-kernelspec install --user cling-cpp11
```
refer to [this](https://github.com/root-project/cling)
## remote connect
```
```
refer to [this](https://zhuanlan.zhihu.com/p/72920198)

