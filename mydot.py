#!/usr/bin/env python3
import argparse
from enum import Enum
import glob
import os
import re
import shutil
import sys
from typing import Pattern, Protocol

DefTarget: str = "target"

SchemaGitHub: str = "github"
SchemaFile: str = "file"
SchemaTemplate: str = "template"

RepoDir: str = ".repo"
ConfName: str = "dotconf"
FilesName: str = "files"
ConfPattern: Pattern = re.compile("[ \t]+")
TemplatePattern: Pattern = re.compile("^\\$template\\((.*)\\)$")
KeywordPattern: Pattern = re.compile("\\${([^}]+)}")


class TemplateKeyword(Enum):
    GitHubFile = "github_file"


class ConfData(Protocol):
    def save(self, main_dir: str, d: str):
        """保存配置数据到指定目录"""
        pass

    def fill(self, d: str, key: str, alts: list[str]) -> list[str]:
        """根据关键字填充模板内容"""
        return []

    @staticmethod
    def prepare_conf(
        app: str, conf: list[str], datas: list["ConfData"]
    ) -> "ConfData | None":
        """根据配置类型创建对应的配置数据对象"""
        match conf[0]:
            case GitHubData.name:
                if len(conf) > 3:
                    return GitHubData(conf[1], conf[2], conf[3:])
                else:
                    return GitHubData(conf[1], conf[2])
            case FileData.name:
                if len(conf) > 2:
                    return FileData(app, conf[1], conf[2])
                else:
                    return FileData(app, conf[1])
            case TemplateData.name:
                if len(conf) > 2:
                    return TemplateData(app, datas, conf[1], conf[2])
                else:
                    return TemplateData(app, datas, conf[1])


class GitHubData(ConfData):
    name = SchemaGitHub

    def __init__(
        self, git_repo: str, target_dir: str, target_files: list[str] | None = None
    ):
        self.git_repo = git_repo
        self.target_dir = target_dir.replace("${repo}", git_repo)
        self.target_files = target_files

    def checkout(self, main_dir: str, d: str):
        """从本地 Git 仓库检出文件到目标目录"""
        os.makedirs(d, exist_ok=True)
        full_target_path = os.path.join(d, self.target_dir)
        try:
            os.makedirs(full_target_path)
        except FileExistsError:
            print("SKIP checkout for existing dir %s" % full_target_path)
            return
        files = " ".join(self.target_files) if self.target_files else ""
        full_git_repo_path = os.path.join(main_dir, RepoDir, self.git_repo)
        code = os.system(
            "git --git-dir=%s archive HEAD %s|tar xf - -C %s"
            % (full_git_repo_path, files, full_target_path)
        )
        if 0 == code:
            os.system(
                "git --git-dir=%s show-ref --head HEAD > %s/ref_id"
                % (full_git_repo_path, full_target_path)
            )
        else:
            raise RuntimeError("Check failed with %d" % code)

    def clone(self, main_dir: str):
        """从 GitHub 克隆仓库到本地"""
        full_repo_path = os.path.join(main_dir, RepoDir)
        os.makedirs(full_repo_path, exist_ok=True)
        full_git_repo_path = os.path.join(full_repo_path, self.git_repo)
        code = os.system(
            "git clone --depth=1 --bare https://github.com/%s.git %s"
            % (self.git_repo, full_git_repo_path)
        )
        if 0 != code:
            raise RuntimeError("Clone failed with %d" % code)

    def fetch(self, main_dir: str):
        """从远程仓库获取最新更新"""
        full_git_repo_path = os.path.join(main_dir, RepoDir, self.git_repo)
        code = os.system("git --git-dir=%s fetch -q" % full_git_repo_path)
        if 0 != code:
            raise RuntimeError("Fetch failed with %d" % code)

    def save(self, main_dir: str, d: str):
        """保存 GitHub 仓库内容到目标目录"""
        git_repo_path = os.path.join(main_dir, RepoDir, self.git_repo)
        if os.path.exists(git_repo_path):
            self.fetch(main_dir)
        else:
            self.clone(main_dir)
        self.checkout(main_dir, d)

    def fill_dir(self, d: str, subdir: str, alts: list[str]) -> list[str]:
        """根据关键字返回补全的文件夹内文件路径"""
        for alt in alts:
            final_dir = os.path.join(d, subdir)
            if os.path.isdir(final_dir):
                matches = glob.glob(alt, root_dir=final_dir)
                if len(matches) > 0:
                    matches.sort()
                    return [os.path.join(subdir, x) for x in matches]
        return []

    def fill(self, d: str, key: str, alts: list[str]) -> list[str]:
        """根据关键字返回 GitHub 文件路径"""
        res = []
        match key:
            case TemplateKeyword.GitHubFile:
                if self.target_files:
                    for file in self.target_files:
                        relative_path = os.path.join(self.target_dir, file)
                        full_path = os.path.join(d, relative_path)
                        if os.path.isfile(full_path):
                            res.append(relative_path)
                        else:
                            res.extend(self.fill_dir(d, relative_path, alts))
                else:
                    res.extend(self.fill_dir(d, self.target_dir, alts))
        return list(dict.fromkeys(res))


class FileData(ConfData):
    name = SchemaFile

    def __init__(self, app: str, file: str, target_dir: str | None = None):
        self.app = app
        self.file = file
        self.target_dir = target_dir

    def save(self, main_dir: str, d: str):
        """保存本地文件到目标目录"""
        full_file_path = os.path.join(main_dir, self.app, FilesName, self.file)
        full_target_path = (
            os.path.join(d, self.target_dir, self.file)
            if self.target_dir
            else os.path.join(d, self.file)
        )

        if os.path.isdir(full_file_path):
            shutil.copytree(full_file_path, full_target_path)
        else:
            shutil.copy(full_file_path, full_target_path)


class TemplateData(ConfData):
    name = SchemaTemplate

    def __init__(
        self,
        app: str,
        datas: list[ConfData],
        template_file: str,
        target_dir: str | None = None,
    ):
        self.app = app
        self.datas = datas
        self.template_file = template_file
        if not template_file.endswith(".template"):
            raise RuntimeError("Template file should end with .template")
        self.target_dir = target_dir

    def get_filled(self, d: str, key_mat: str, to_fill: str) -> list[str]:
        """根据关键字匹配结果填充模板内容"""
        result = []
        key_conf = key_mat.split(":")
        keyword = key_conf[0]
        alts = key_conf[1:]
        for data in self.datas:
            lines = data.fill(d, keyword, alts)
            if lines:
                for line in lines:
                    result_line = re.sub(KeywordPattern, line, to_fill)
                    if result_line:
                        result.append(result_line + "\n")
        return result

    def process_line(self, d: str, line: str) -> list[str]:
        """处理模板文件中的单行内容"""
        template_match = TemplatePattern.match(line.strip())
        if template_match:
            template_content = template_match.group(1)
            keyword_match = KeywordPattern.findall(template_content)
            if len(keyword_match) > 0:
                return self.get_filled(d, keyword_match[0], template_content)
            else:
                print("no keyword in template %s" % template_content)
                return []
        return [line]

    def save(self, main_dir: str, d: str):
        """处理模板文件并保存到目标目录"""
        full_template_path = os.path.join(
            main_dir, self.app, FilesName, self.template_file
        )
        result_file = self.template_file.replace(".template", "")
        full_target_path = (
            os.path.join(d, self.target_dir, result_file)
            if self.target_dir
            else os.path.join(d, result_file)
        )
        with open(full_template_path, "r") as f:
            with open(full_target_path, "w") as w:
                for line in f:
                    for content in self.process_line(d, line):
                        w.write(content)


def get_apps(d: str) -> list[str]:
    """获取包含配置文件的应用程序目录列表"""
    out = []
    dirs = os.listdir(d)
    for x in dirs:
        if os.path.exists(os.path.join(d, x, ConfName)):
            out.append(x)
    return out


def parse_config(d: str, app: str) -> list[ConfData]:
    """解析指定应用的配置文件"""
    conf_out: list[ConfData] = []
    with open(os.path.join(d, app, ConfName)) as f:
        for line in f:
            conf = re.split(ConfPattern, line.strip())
            data = ConfData.prepare_conf(app, conf, conf_out)
            if data:
                conf_out.append(data)

    return conf_out


def parse_args():
    """解析命令行参数"""
    my_name = sys.argv[0]
    my_dir = os.path.dirname(my_name)
    if len(my_dir) == 0:
        my_dir = "."
    parser = argparse.ArgumentParser(prog=my_name)
    parser.add_argument("--main-dir", type=str, default=my_dir)
    parser.add_argument("--work-dir", type=str, default=DefTarget)
    args = parser.parse_args()
    return args


def show_progress(progress: float):
    """显示进度条"""
    barLength, status = 60, ""
    if progress >= 1.0:
        progress, status = 1, "\r\n"
    block = int(round(barLength * progress))
    text = "\r[{}] {:.0f}% {}".format(
        "#" * block + "-" * (barLength - block), round(progress * 100, 0), status
    )
    sys.stdout.write(text)
    sys.stdout.flush()


LIST_APP_PROGRESS = 0.05
PATH_APP_PROGRESS = 0.1


def main():
    """主函数：解析配置并执行保存操作"""
    args = parse_args()
    main_dir = args.main_dir
    work_dir = args.work_dir

    progress = 0.0
    show_progress(progress)

    apps = get_apps(main_dir)
    progress += LIST_APP_PROGRESS
    show_progress(progress)

    confs = []

    step_count = len(apps) if len(apps) > 0 else 1
    step = PATH_APP_PROGRESS / step_count
    for app in apps:
        confs.extend(parse_config(main_dir, app))
        progress += step
        show_progress(progress)

    step_count = len(confs) if len(confs) > 0 else 1
    step = (1 - LIST_APP_PROGRESS - PATH_APP_PROGRESS) / step_count
    for conf in confs:
        conf.save(main_dir, work_dir)
        progress += step
        show_progress(progress)

    if progress < 1.0:
        show_progress(1)


if __name__ == "__main__":
    main()
