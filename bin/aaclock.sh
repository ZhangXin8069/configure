#!/usr/bin/env bash
#
# Author: LKJ
# Date: 2013/5/14
# Email: liungkejin@gmail.com
#
_PATH=$(
    cd "$(dirname "$0")"
    pwd
)
_NAME=$(basename "$0")
echo "###${_NAME} in ${_PATH} is running...:$(date "+%Y-%m-%d-%H-%M-%S")###"
asciinumber=(
    '    .ZHANGx           ,:XIN          :ZHANGNB        .LOVEXIN9                dOOp       ZHANGXINNB           1YYDS1    ILOVEZHANGXIN       5SHIREN.         iZXYYDS    '
    '   ILOVEXINE3       iZXYYDS         RIPZHANGXIN      ZHANGXINNBb             ZHANG      5GONGCHNAGX        :ZHANGNB,    IZHANGTIANXIU     SHISHEN8SHI      1GETIANCAI5  '
    '  XIN.    ZXNB      ZX" XIN         ZX      XINc     :"      XIN            ZHANG3      9NB               AWSL.                  :ZX.    1SEs     :XIN    6ZX9     XINc '
    ' ,ZXc      XIN          XIN                  XIN             zNB:          XIN XIN      XIN              XIN                     XIN     XIN       XIN    XIN       XIN '
    ' XIN       jBB8         XIN                  XIN             XIN          XIN  XIN      ZX              XIN   ..                XIN      XINc     :ZX6   ,ZX6       zNB '
    ' XIN        XIN         XIN                 :ZX6       .::iYYDS          XIN   XIN     .ZHANGXIN        ZX66BUYANLE            XIN        LOVEi  bBB8    .XIN       :ZX.'
    '.XIN        XIN         XIN                 XIN        ZHANGNB         .ZXc    XIN     :I2BFOREVER     4RENWC.".DDDD.         XIN.          ZHANGNB       XINc     :XIN '
    ' XIN        XIN         XIN               :XIN            "iYYDS      :ZX      ZX6             ZXNB    XINc       XIN        .ZX6         ZXNB:.5SHUI      ZHANGXINYYDS '
    ' XIN       .XIN         XIN              zXIN                6XIN    iSEE666ZHANGX2b            XIN    XIN        1TH,       XIN         XIN      ,XIN      .xZHANG XIN '
    ' XIN       3EE:         XIN            .XIN,                  XIN    ILOVEXINFOREVER            XIN    5NB        zNB:      XIN         7ZX8       yES1            :ZX: '
    ' .NBy      XIN          XIN           zXIN                    XIN              ZX6              XIN     XIN       XIN      1SB:         kWOc       4WOc           ZXNB  '
    '  RIP9    XIN.          XIN         zXIN             Z       RIP9              XIN     j      :XIN      ZXNB     XINc     .XIN           XIN:     .XIN          1SHEN   '
    '   iZHANGXIN.           XIN        ILOVEZHANGXIN    iDONTLOVEZB8               ZXc    RIPZHANGXIN        iSZHENSHUI8     .XIN             RIPZHANGXIN      5SHUOWAN     '
    '     ZHANG3             RIP        7ZX8NBFOREVER     :IBUSHI0.                 xZx     9ZHANGXc            4RENMA:       1SB                WBUSHI1        ZHANG"       '
);
asciidot=(
    ' @@ '
    ' @@ '
);
len=${#asciinumber[@]};
#共有三个参数,
#第一个是所要打印的数字,
#第二个是之前打印的数字个数，
#第三个是之前打印的点的个数
function print_number {
    start=$(($1*17));
    start_y=$(($2*17+$3*4+$beg_y));
    for (( i = 0; i < len; i++ )); do
        echo -ne "\033[$((beg_x+i));${start_y}H\033[1;32m${asciinumber[$i]:$start:17}\033[0m";
    done
}
#print_dot有两个参数
#第一个参数是之前打印的数字个数
#第二个参数是之前打印的点的个数
function print_dot {
    local pt=$(($1*17+$2*4+beg_y));
    for (( j = 0; j < 2; j++ )); do
        echo -ne "\033[$((beg_x+j+3));${pt}H\033[1;32m${asciidot[$j]}\033[0m";
        echo -ne "\033[$((beg_x+j+10));${pt}H\033[1;32m${asciidot[$j]}\033[0m";
    done
}
function old_value {
    orows=`tput lines`; beg_x=$((orows/2-6));
    ocols=`tput cols`;  beg_y=$((ocols/2-54));
    ohur=$((10#`date +%H`));
    omin=$((10#`date +%M`));
    osec=$((10#`date +%S`));
    print_number $((ohur/10)) 0 0; print_number $((ohur%10)) 1 0;
    print_dot 2 0;
    print_number $((omin/10)) 2 1; print_number $((omin%10)) 3 1;
    print_dot 4 1;
    print_number $((osec/10)) 4 2; print_number $((osec%10)) 5 2;
}
function print_all {
    t_rows=`tput lines`; beg_x=$((t_rows/2-6));
    t_cols=`tput cols`;  beg_y=$((t_cols/2-54));
    if [[ $t_rows -ne $orows || $t_cols -ne $ocols ]]; then
        orows=$t_rows;
        ocols=$t_cols;
        check_win $orows $ocols;
        old_value;
    fi
    hur=$((10#`date +%H`));
    hft=$((hur/10)); hsd=$((hur%10));
    if [[ $ohft -ne $hft ]]; then
        print_number $hft 0 0;
        ohft=$hft;
    fi
    if [[ $ohsd -ne $hsd ]]; then
        print_number $hsd 1 0;
        ohsd=$hsd;
    fi
    min=$((10#`date +%M`));
    mft=$((min/10)); msd=$((min%10));
    if [[ $omft -ne $mft ]]; then
        print_number $mft 2 1;
        omft=$mft;
    fi
    if [[ $omsd -ne $msd ]]; then
        print_number $msd 3 1;
        omsd=$msd;
    fi
    sec=$((10#`date +%S`)); #出现(())bug的原因：date +%S < 10 的时候会有前置0
    #所以((08/10))会出错,但是使用expr不会出现错误,let也会有此错误
    #解决方法是$((10#08/10));
    sft=$((sec/10)); ssd=$((sec%10));
    if [[ $osft -ne $sft ]]; then
        print_number $sft 4 2;
        osft=$sft;
    fi
    if [[ $ossd -ne $ssd ]]; then
        print_number $ssd 5 2;
        ossd=$ssd;
    fi
}
function check_win {
    if [[ $1 -lt 14 || $2 -lt 110 ]]; then
        clear;
        echo -ne "\033[8;15;120t"; #change the window size
    fi
    clear; #若窗口改变则重新刷新
}
function INIT {
    tput smcup; #保存屏幕
    check_win `tput lines` `tput cols`;
    trap 'EXIT;' SIGINT; #将光标重新设置为白色
    tput civis; #设置光标不可见
    old_value;
}
function EXIT {
    tput cvvis; #使光标可见
    tput rmcup; #恢复屏幕
    exit 0;
}
INIT;
while true; do
    read -t 1 -n 1 anykey;
    if [[ $? -eq 0 ]]; then
        EXIT;
    fi
    print_all;
    #    if sleep 0.3 &> /dev/null; then
    #	sleep 1;
    #    fi;
done
exit 0;
echo "###${_NAME} in ${_PATH} is done......:$(date "+%Y-%m-%d-%H-%M-%S")###"
