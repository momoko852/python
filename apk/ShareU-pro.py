# -*- coding: utf-8 -*-

import os
import urllib3
import sys

sys.path.append(os.path.join(os.path.dirname(os.environ["WORKSPACE"]), "TestTool"))
from apk.common import *

urllib3.disable_warnings()
currentdir = os.getcwd()
BUILD_NUMBER = os.environ["BUILD_NUMBER"]
Title = os.environ["Title"]
Branch = os.environ["Branch"]
project="ShareU"
Bundle_Version_Name = os.environ["VersionName"].strip()
apk_dir = os.path.join(currentdir, "app/build/outputs/apk/normal/release")
temp_work_dir = os.getenv("WORK_DIRS", "")
work_dir = temp_work_dir if temp_work_dir != "" else "/root"
mapdir = os.path.join(currentdir,"app/build/outputs/mapping/normal/release")
SizeCheck=os.getenv("SizeCheck","true")

def startBuildApk():
    logger.info("**************开始构建APK**************")
    cmd_build = "./gradlew clean  assembleRelease  --configure-on-demand --daemon --parallel --build-cache --stacktrace"
    builddata = {
        "msgtype": "markdown",
        "markdown": {
            "title": "ShareU编译失败",
            "text": "#### 编译失败-" + Branch + "(#" + BUILD_NUMBER + ")" \
                    + "\n  > ##### [查看日志](http://ci.flatincbr.com/job/Game-Quiz-release/" + BUILD_NUMBER + "/console)"
        }
    }
    code = oscmd(cmd_build)
    if code != 0:
        dingding(builddata)
        raise Exception("编译异常")
    apk_path_temp = os.path.join(apk_dir, file_name(apk_dir, ".apk"))
    pkg_name, version_name, version_code = get_apk_info(apk_path_temp)
    apk_path = rename(file_path=apk_path_temp, project=project, versionName=version_name, versionCode=version_code,
                      is_test=False)
    logger.info("**************APK打包完成**************")
    return pkg_name, apk_path,version_name,version_code

def dingding(data):
    secret = 'SEC9d6b8e0e95f7345c1172674790dcef909bdfed31404ed923ff85e51acba57ada'
    asscess_token = '85f8299ffe02ba985d379caab3892cacfeb621203c458ba9e26ebeec21c9aea8'
    return dingding_robot(data=data, assess_token=asscess_token, secret=secret)


def modiyProFile(path):
    data = get_properties(path)
    # 如果版本为默认值，自动加1
    if Bundle_Version_Name == "1.0.0.0":
        version_list = data["VERSIONNAME"].split(".")
        num = int(version_list[-1]) + 1
        version_list[-1] = str(num)
        version = ".".join(version_list)
    else:
        version = Bundle_Version_Name
    logger.info("生成的版本号为："+str(version))
    version_code = get_version_code(version)
    logger.info("生成的版本号为："+str(version_code))

    play = {
        "VERSIONCODE": version_code,
        "VERSIONNAME": version
    }
    modiy_properties_file(path, **play)


if __name__ == "__main__":
    gradle_properties_path = os.path.join(currentdir, 'gradle.properties')
    modiyProFile(gradle_properties_path)
    pkg_name, apk_path,version_name,version_code = startBuildApk()
    logger.info("恢复gradle.properties：")
    oscmd("git checkout -- " + gradle_properties_path)
    try:
        apk_content = upload_apk(apk_path)
        get_apk_size(apk_path)
        if apk_content["status"] != 1:
            raise Exception("上传apk失败!原因为：" + json.dumps(apk_content))
        apk_url = apk_content["data"]["oss_url"]
        logger.info("获取到的apk下载链接为：" + str(apk_url))

        temp_mapping_path=os.path.join(mapdir, "mapping.txt")
        mapping_path = rename(file_path=temp_mapping_path, is_test=False, project=project, is_for32=False,
                              versionName=version_name, versionCode=version_code)

        mapping_content = upload_file(mapping_path, is_test=False)
        if mapping_content["status"] != 1:
            raise Exception("上传apk失败!原因为：" + json.dumps(mapping_content))
        mapping_url = mapping_content["data"]["oss_url"]

        playload = {
            "name": os.path.split(apk_path)[1],
            "version": version_name,
            "branch": Branch,
            "pkg_name": pkg_name,
            "pf": "android",
            "status": 0,
            "title": Title,
            "build_num": BUILD_NUMBER,
            "attachment": mapping_url,
            "sign_ver":2
        }
        cms_add_content = add_info_to_cms(is_test=False, **playload)
        if cms_add_content["status"] != 1:
            raise Exception("信息上传到cms失败,信息为：" + json.dumps(cms_add_content))

        qrcode_url = makeqrcode(apk_dir=os.path.dirname(apk_path), url=apk_url, project=project, is_test=False,
                                build_num=BUILD_NUMBER)

        Data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "ShareU正式包(#" + BUILD_NUMBER + ")",
                "text": "#### ShareU正式包(#" + BUILD_NUMBER + ")-" + Branch \
                        + "\n  > ##### 更新日志：" + Title \
                        + "\n  > ##### [" + os.path.split(apk_path)[1] + "](" + apk_url + ")"
                        + "\n  > ##### [" + os.path.split(mapping_path)[1] + "](" + mapping_url + ")"
                        + "\n > ![screenshot](" + qrcode_url + ")"
            }
        }
        dingding(Data)

        commit_code_before(Branch=Branch, gradle_properties_path=gradle_properties_path)
        modiyProFile(gradle_properties_path)
        commit_code_after(Branch=Branch, gradle_properties_path=gradle_properties_path, version_name=version_name,build_num=BUILD_NUMBER)
    except ProcessExpection as e:  # 提交代码异常可以继续运行程序
        error_data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "上传代码异常",
                "text": "#### 上传代码失败",
            }
        }
        dingding(error_data)
    except Exception as e:
        logger.info("发生异常为：" + str(e))
        traceback.print_exc()
        error_data = {
            "msgtype": "markdown",
            "markdown": {
                "title": "打包过程异常",
                "text": "#### 打包过程异常，异常原因为：\n\n" + str(e),
            }
        }
        dingding(error_data)
        raise e
    if SizeCheck=="true":
        dingding_robot_token="https://oapi.dingtalk.com/robot/send?access_token=85f8299ffe02ba985d379caab3892cacfeb621203c458ba9e26ebeec21c9aea8"
        virustotalscanAndSizecheck(url=apk_url, b_num=BUILD_NUMBER, pkgname=pkg_name, versionname=version_name,
                                   cSize="NA", token=dingding_robot_token, project=project)
