sudo cpupower -c all frequency-set -d 1400000 -u 4500000 -g conservative
sudo cpupower idle-set -e 0
sudo cpupower idle-set -e 1
sudo cpupower idle-set -d 2
sudo cpupower idle-set -e 3
watch -n 0.1 sudo cpupower monitor
