/*
 * unix-op.out - 泛 unix 隐蔽启动器
 * 唯一目的: 以不易识别的进程名运行同目录的 oopencode.sh，
 *           避免 htop/ps/top 等识别出 "opencode" 明文进程，
 *           防止在服务器平台暴露用户 agent 信息。
 *
 * 原理:
 *   - 解析自身真实路径(/proc/self/exe 或 argv[0])，定位同目录 oopencode.sh
 *   - fork 子进程，把脚本重定向到 stdin，exec bash -s：
 *     * 进程 cmdline 仅显示 "unix-op -s [参数]"（脚本路径不出现在命令行）
 *     * 进程 comm 显示 bash（htop/ps/top 均无 opencode 明文）
 *   - 原始参数(-p/-q/-k/-g/-f 等)透传给脚本；退出码透传
 *
 * 编译: gcc -O2 -Wall -o unix-op.out unix-op.c
 * 用法: unix-op.out [-p|-q|-k|-g|-f]
 */
#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <libgen.h>
#include <fcntl.h>
#include <sys/wait.h>

#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

static char *self_dir(char *buf, size_t n) {
#ifdef __linux__
    ssize_t len = readlink("/proc/self/exe", buf, n - 1);
    if (len > 0) {
        buf[len] = '\0';
        char *slash = strrchr(buf, '/');
        if (slash) {
            *slash = '\0';
            return buf;
        }
    }
#elif defined(__APPLE__)
    uint32_t size = (uint32_t)n;
    if (_NSGetExecutablePath(buf, &size) == 0) {
        char *slash = strrchr(buf, '/');
        if (slash) {
            *slash = '\0';
            return buf;
        }
    }
#endif
    return NULL;
}

int main(int argc, char **argv) {
    char self[PATH_MAX] = {0};
    char script[PATH_MAX];
    char *dir = self_dir(self, sizeof(self));

    if (!dir) {
        /* fallback: 按 argv[0] 所在目录 */
        if (argc > 0 && argv[0] && strchr(argv[0], '/')) {
            strncpy(self, argv[0], sizeof(self) - 1);
            self[sizeof(self) - 1] = '\0';
            char *slash = strrchr(self, '/');
            if (slash) {
                *slash = '\0';
                dir = self;
            }
        }
    }
    if (!dir || !*dir) {
        fprintf(stderr, "unix-op: cannot locate self directory\n");
        return 127;
    }

    if (snprintf(script, sizeof(script), "%s/oopencode.sh", dir) >= (int)sizeof(script)) {
        fprintf(stderr, "unix-op: script path too long\n");
        return 127;
    }
    int fd = open(script, O_RDONLY);
    if (fd < 0) {
        fprintf(stderr, "unix-op: cannot open %s\n", script);
        return 127;
    }

    /* 构造 bash 参数: argv[0] 伪装 + /dev/fd/3 脚本 + 透传原始参数 */
    char **args = malloc((size_t)(argc + 3) * sizeof(char *));
    if (!args) {
        perror("malloc");
        close(fd);
        return 127;
    }
    size_t n = 0;
    args[n++] = (char *)"unix-op";        /* 伪装的 argv[0] */
    args[n++] = (char *)"/dev/fd/3";       /* 脚本经 fd 3 传入(见下方 dup2) */
    for (int i = 1; i < argc; i++)         /* 透传 -p/-q/-k/-g/-f 等 */
        args[n++] = argv[i];
    args[n] = NULL;

    pid_t pid = fork();
    if (pid < 0) {
        perror("fork");
        free(args);
        close(fd);
        return 127;
    }
    if (pid == 0) {
        /*
         * 脚本放到 fd 3 而非 stdin:
         *  - 命令行不出现脚本路径(ps/htop/top 仅见 "unix-op /dev/fd/3 ...")
         *  - stdin(0) 保留给 opencode 交互输入, 不会被脚本文件占据
         * 注入 OPENCODE_SCRIPT_DIR 供脚本定位同目录资源(prompt 模板等),
         * 因 /dev/fd/3 模式下 BASH_SOURCE 指向 /dev/fd/3, dirname 失效。
         */
        setenv("OPENCODE_SCRIPT_DIR", dir, 1);
        if (dup2(fd, 3) < 0) {
            perror("dup2");
            _exit(127);
        }
        if (fd != 3)           /* fd 恰为 3 时 dup2 是 no-op，不能 close */
            close(fd);
        execvp("bash", args);
        perror("execvp bash");
        _exit(127);
    }
    free(args);
    close(fd);

    int status;
    if (waitpid(pid, &status, 0) < 0) {
        perror("waitpid");
        return 127;
    }
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return 127;
}
