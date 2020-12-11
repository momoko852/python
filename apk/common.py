# 抽离测试相关的公共模块，以便复用
'''
要求：
    1、禁止定义全局变量，所有的变量都定义到函数里面
    2、没有主函数，都以函数模块形式存在
    3、每个函数都必须对函数参数说明，以及作用说明
    4、禁止使用print添加日志,使用logger.info替代
'''
import base64
import fileinput
import hashlib
import hmac
import json
import os
import psutil
import re
import shutil
import subprocess
import time
import traceback
import urllib
import zipfile

import qrcode
import requests
from PIL import Image
from logzero import logger


####私有函数，禁止被外部调用
class ProcessExpection(Exception):
    def __init__(self, err='PreconditionsErr'):
        Exception.__init__(self, err)


def _is_exits(*path_list):
    '''判断路径是否存在'''
    for path in path_list:
        if not os.path.exists(path):
            raise Exception("'" + path + "' is not exists")


def _get_variable():
    '''获取环境变量等全局变量'''
    data = {}
    temp_work_dir = os.getenv("WORK_DIRS", "")
    work_dir = temp_work_dir if temp_work_dir != "" else "/home/jenkins"
    bundle_jar_dir = os.path.join(temp_work_dir, "jar_file") if temp_work_dir != "" else "/home1/root/jar_file"
    bundle_convert_jar = os.path.join(bundle_jar_dir, "bundletool-all-0.13.0.jar")
    data["bundletool"] = bundle_convert_jar
    aapt_path = work_dir + "/android-sdk-linux/build-tools/27.0.3/aapt"  # 解析工具aapt地址
    apksigner_path = work_dir + "/android-sdk-linux/build-tools/29.0.3/apksigner"  # 签名工具 apksigner地址
    data["aapt_path"] = aapt_path
    data["apksigner_path"] = apksigner_path
    data["work_dir"] = work_dir
    return data


def _getSign(secret):
    '''
    根据秘钥获取时间戳和签名
    :param secret: 秘钥地址
    :return: 时间戳、签名
    '''
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return timestamp, sign


def _getApkIcon(apkdir):
    '''
    根据apk的目录获取下面的apk的icon
    :param apkdir: apk的目录地址
    :return: icon的路径
    '''
    logger.info("begin getApkIcon")
    apk_path = os.path.join(apkdir, file_name(apkdir, ".apk"))  # apk地址
    aapt_path = _get_variable()["aapt_path"]
    cmd = "%s dump badging %s | grep application-icon" % (aapt_path, apk_path)
    output, _ = putcmd(cmd)
    iconPath = (output.split()[0])[22:-1]
    logger.info("iconPath:" + iconPath)
    zip = zipfile.ZipFile(apk_path)
    iconData = zip.read(iconPath)
    saveIconName = os.getcwd() + "/icon.png"
    logger.info("saveIconName:" + saveIconName)

    with open(saveIconName, 'w+b') as saveIconFile:
        saveIconFile.write(iconData)
    return saveIconName


### 共有函数，可以被外部调用

def oscmd(cmd):
    '''
    执行命令，并输出返回
    :param cmd: 执行的命令
    :return: 命令执行完成的返回码
    '''
    logger.info("执行命令：" + str(cmd))
    code = os.system(cmd)
    logger.info("执行命令返回码为：" + str(code))
    return code


def putcmd(cmd):
    '''
    执行命令函数
    :param cmd: 执行的命令
    '''
    logger.info("执行命令：" + cmd)
    cmd = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    out = str(cmd.stdout.read(), encoding="utf-8")
    error = str(cmd.stderr.read(), encoding="utf-8")
    if len(out.strip()) > 0:
        if isinstance(out, list or dict):
            logger.info("命令输出为：")
            logger.info(json.dumps(out, indent=4))
        else:
            logger.info("命令输出为：" + out)
    elif len(error.strip()) > 0:
        if isinstance(error, list or dict):
            logger.info("命令输出为：")
            logger.info(json.dumps(error, indent=4))
        else:
            logger.info("命令错误输出为：" + error)
    return out, error


def file_name(file_dir, ftype):
    '''
    根据文件路径查找后缀为ftype的文件
    :param file_dir: 文件目录
    :param ftype: 需要查找的文件文件后缀
    :return: 文件地址
    '''
    L = []
    for root, dirs, files in os.walk(file_dir):
        for file in files:
            if os.path.splitext(file)[1] == ftype:
                L.append(os.path.join(file))
    logger.info("在目录：%s，找到文件：%s" % (file_dir, str(L)))
    return L[0]


def get_properties(properties_path):
    """
    :to:将properties里面的内容转成字典
    :param properties_path:properties文件路径
    :return 返回字典
    """
    _is_exits(properties_path)
    data = {}
    with open(properties_path, "r") as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith("#"):
            continue
        if line.strip("\n").strip():
            k, v = line.split("=")
            data[str(k).strip()] = str(v).strip("\n")
    return data


def bundle_convert(aab_path, key_properties, key_path, mode="universal"):
    '''
    :to:将aab转换为apk，并加密。参考文档：https://developer.android.google.cn/studio/command-line/bundletool?hl=zh-cn
    :param aab_path:aab文件的绝对路径
    :param key_properties:秘钥.properties配置文件地址，固定格式为
            ``` ks_name=xxx.keystore
                ks_pass=xxxx
                ks_key_alias=xxxx
                key_pass=xxxxx
            ```
    :param key_path:xxx.keystore文件目录
    :param mode:默认universal，如果此值为空，则表示将分32位，64位打包
    :return:转换成功的apk的路径，当为多apk文件时，返回apk文件目录
    '''
    logger.info("开始转换aab到apk")
    _is_exits(aab_path, key_properties, key_path)
    aab_dir = os.path.dirname(aab_path)
    apks_path = os.path.join(aab_dir, "bundle.apks")
    if os.path.exists(apks_path):
        shutil.rmtree(apks_path)
    if mode != "universal":
        mode_string = ""
    else:
        mode_string = "--mode=universal"
    properties_data = get_properties(key_properties)
    ks_path = os.path.join(key_path, "{ks_name}".format(ks_name=properties_data["ks_name"]))

    convert_cmd = "java -jar {bundle_jar} build-apks {mode} " \
                  "--bundle={aab_path} --output={apks_path} --ks={ks_path} --ks-pass='pass:{ks_pass}'" \
                  " --ks-key-alias={ks_key_alias} --key-pass='pass:{key_pass}'".format(
        mode=mode_string,
        bundle_jar=_get_variable()["bundletool"],
        aab_path=aab_path,
        apks_path=apks_path,
        ks_path=ks_path,
        ks_pass=properties_data["ks_pass"],
        ks_key_alias=properties_data["ks_key_alias"],
        key_pass=properties_data["key_pass"])

    putcmd(convert_cmd)
    unzip_cmd = "unzip -o {apks_path} -d {aab_dir}".format(apks_path=apks_path, aab_dir=aab_dir)
    putcmd(unzip_cmd)
    logger.info("解压成功")
    logger.info("aab转到apk完成")
    if mode == "universal":
        logger.info("mode为：universal，返回路径为：" + str(os.path.join(aab_dir, file_name(aab_dir, ".apk"))))
        return os.path.join(aab_dir, file_name(aab_dir, ".apk"))
    else:
        logger.info("mode为：" + str(mode) + "，返回路径为：" + str(os.path.join(aab_dir, "standalones")))
        return os.path.join(aab_dir, "standalones")


def makeqrcode(apk_dir, url, build_num, project, is_test=True):
    '''
    根据url生成二维码
    :param apk_dir:apk的地址，主要是解析apk里面的icon
    :param url: url地址
    :param build_num: 构建号
    :param project: 项目
    :param is_test: 是否是测试环境
    :return: 二维码的地址
    '''
    path = _getApkIcon(apk_dir)
    # 判断图片大小，太大则变小
    img_obj = Image.open(path)
    width = int(img_obj.width)  # 图片的宽
    hight = int(img_obj.height)  # 图片的高
    if width > 50 or hight > 50:
        out = img_obj.resize((50, 50), Image.ANTIALIAS)
        out.save(path, "png")

    work_dir = _get_variable()["work_dir"]
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image()
    img = img.convert("RGBA")
    icon = Image.open(path).convert("RGBA")
    img_w, img_h = img.size
    factor = 4
    size_w = int(img_w / factor)
    size_h = int(img_h / factor)

    icon_w, icon_h = icon.size

    if icon_w > size_w:
        icon_w = size_w
    if icon_h > size_h:
        icon_h = size_h

    icon = icon.resize((icon_w, icon_h), Image.ANTIALIAS)
    w = int((img_w - icon_w) / 2)
    h = int((img_h - icon_h) / 2)
    img.paste(icon, (w, h), icon)

    temp_save_img = os.path.join(work_dir, "images/{}_images".format(project))
    if os.path.exists(temp_save_img):
        shutil.rmtree(temp_save_img)
    os.makedirs(temp_save_img)
    unixtime = int(time.time())
    name = build_num + project + "_" + str(unixtime) + "_test.png" if is_test else build_num + project + "_" + str(unixtime) + "_release.png"
    temp_save_img_path = os.path.join(temp_save_img, name)
    img.save(temp_save_img_path, format="png")
    content = upload_file(temp_save_img_path, is_test)

    if content["status"] != 1:
        logger.info("上传图片返回内容为：" + json.dumps(content))
        raise Exception("图片上传失败")
    image_download_url = content['data']['oss_url']
    logger.info("二维码的下载地址为：" + (image_download_url))
    return image_download_url


def get_apk_info(apk_path):
    '''
    根据apk
    :param apk_path:apk的路径
    :return:返回解析出来的包名，版本号，版本名
    '''
    _is_exits(apk_path)
    aapt_path = _get_variable()["aapt_path"]
    get_info_command = "%s dump badging %s" % (aapt_path, apk_path)  # 使用命令获取版本信息
    output, _ = putcmd(get_info_command)  # 执行命令，并将结果以字符串方式返回
    match = re.compile("package: name='(\S+)' versionCode='(\d+)' versionName='(\S+)'").match(
        output)  # 通过正则匹配，获取包名，版本号，版本名称
    if not match:
        logger.info("版本信息校验出错，内容为：")
        logger.info(output)
        raise Exception("不能获取版本信息")
    versionCode = match.group(2)
    versionName = match.group(3)
    pkgName = match.group(1)
    logger.info("解析出来的版本号为：" + str(versionCode) + "，解析出来的版本名为：" + str(versionName) + ",解析出来的包名为：" + str(pkgName))
    return pkgName, versionName, versionCode


def get_apk_size(apkPath):
    '''
    获取文件的大小
    :param apkPath: 文件路径
    :return: 返回文件的大小
    '''
    size = round(float(os.path.getsize(apkPath)) / (1024 * 1024), 2)
    logger.info("获取apk的大小为：" + str(size) + "M")
    return str(size) + "M"


def dingding_robot(data, assess_token, secret):
    '''
    发送钉钉消息
    :param data:发送消息的消息体
    :param assess_token: web_hook的token，并不是一长串的url，只需要里面的access_token
    :param secret: 勾选加签生成的字符串
    :return: 发送到钉钉返回的响应
    '''
    timestamp, sign = _getSign(secret)
    dingding_robot_token = "https://oapi.dingtalk.com/robot/send?access_token={assess_token}&&timestamp={timestamp}&sign={sign}".format(
        timestamp=timestamp, sign=sign, assess_token=assess_token)
    headers = {'content-type': 'application/json'}
    r = requests.post(dingding_robot_token, headers=headers, data=json.dumps(data))
    r.encoding = 'utf-8'
    return r.text


def uploadBugly(app_key, app_id, pkgname, product_version, mapping_path):
    '''
    上传mapping文件到bugly
    :param app_key: bugly上面产品的app_key
    :param app_id: bugly上面产品的app_id
    :param pkgname: 报名
    :param product_version:bugly上面显示的mapping文件名字
    :param mapping_path: mapping文件路径
    :return: None
    '''
    _is_exits(mapping_path)
    _, mapname = os.path.split(mapping_path)
    cmd_upload_bugly = '''curl -k \
                        "https://api.bugly.qq.com/openapi/file/upload/symbol?app_key={app_key}&app_id={app_id}" --form "api_version=1" \
                        --form "app_id={app_id}" \
                        --form  "app_key={app_key}" \
                        --form  "symbolType=1"  \
                        --form  "bundleId={pkg_name}" \
                        --form  "productVersion={version_name}" \
                        --form  "channel={channel}" \
                        --form  "fileName={mapping_name}" \
                        --form  "file=@{mapping_path}" --verbose '''.format(
        app_key=app_key,
        app_id=app_id,
        pkg_name=pkgname,
        version_name=product_version,
        channel="",
        mapping_name=mapname,
        mapping_path=mapping_path
    )
    putcmd(cmd_upload_bugly)
    logger.info("mapping文件上传到bugly完成")


def virustotalscanAndSizecheck(url, b_num, pkgname, versionname, cSize, token, project, virusscan=False,
                               sizecheck=True):
    '''
    :param url apk下载地址
    :param b_num 构建号
    :param pkgname 包名
    :param versionname 版本号
    :param cSize 要对比的版本,如果要默认对比上个版本为NA
    :param token 钉钉的推送链接
    :param project 项目名字
    :param virusscan 病毒检查 true/false
    :param sizecheck 大小检查 true/false
    '''
    try:
        cTime = time.strftime("%Y%m%d%H%M%S", time.localtime())
        loginUrl = 'http://172.21.114.252:6688/j_acegi_security_check'
        postData = {'j_username': 'chenhq', 'j_password': 'chq175246'}
        s = requests.session()
        rs = s.post(loginUrl, postData)
        logger.info(rs.status_code)
        c = requests.cookies.RequestsCookieJar()
        c.set('cookie-name', 'cookie-value')
        s.cookies.update(c)
        buildurl = 'http://172.21.114.252:6688/job/VirustotalSG/buildWithParameters'
        data = {'token': 'a47bba49-9c3f-4a29-8caa-9ca2b39f35d6',
                'url': url,
                'virusscan': virusscan,
                'sizecheck': sizecheck,
                'b_num': b_num,
                'pkgname': pkgname,
                'versionname': versionname,
                'compareSize': cSize,
                'project': project,
                'currentTime': cTime,
                'dingtoken': token
                }
        response = s.get(buildurl, params=data)
        logger.info(response.status_code)
        logger.info(response.text)
        if response.status_code == 201:
            logger.info('Trigger virus scan and size check successfully.')
        else:
            logger.info('Trigger virus scan and size check fail.')
    except Exception as e:
        logger.info(traceback.format_exception)
        logger.info(e)
        logger.info('Trigger virus scan and size check exception.')


def add_java_heap(properties_path):
    '''
    根据节点的不同，增加编译时候的内存大小,提高打包速度
    :param properties_path: gradle.properties文件地址
    :return: Node
    '''
    mem = psutil.virtual_memory()
    total = round(float(mem.total) / 1024 / 1024 / 1024, 1)
    used = round(float(mem.used) / 1024 / 1024 / 1024, 1)
    free = round(total - used, 1)
    if free > 12.0: #空闲内存大于12则增大编译内存
        for line in fileinput.input(properties_path, inplace=True):
            if str(line).startswith("org.gradle.jvmargs"):
                print("org.gradle.jvmargs=-Xmx8196m -XX:MaxPermSize=8196m -XX:+HeapDumpOnOutOfMemoryError")
                logger.info("增加编译内存为8g成功")
            else:
                print(str(line).strip("\n"))


def rename(file_path, project, versionName, versionCode, is_test, build_type='', is_for32=False):
    '''
    根据原始文件路径，对文件重新命名，并返回重新命名的文件地址。命名规则为：${project}_${build_type}_v${versionName}_${versionCode}_(test/release).(apk/aab/mapping.text)
    :param file_path:文件路径，仅支持aab/apk/mapping文件地址
    :param build_type:打包类型，可能没有，默认值为空
    :param project:项目名称
    :param is_test:是否是debug包
    :param is_for32:中东打32位包特有参数
    :return:重新生成的文件名字
    '''
    _is_exits(file_path)
    suffix_list = [".txt", ".apk", ".aab"]
    _, name_suffix = os.path.splitext(file_path)
    base_dir = os.path.dirname(file_path)
    if name_suffix not in suffix_list:
        raise Exception("文件仅支持'.apk','.aab','.txt'三种格式")

    currentTime = time.strftime("%Y%m%d%H%M%S", time.localtime())

    if build_type:
        file_name = project + "_" + build_type + "_" + str(versionName) + "_" + str(
            versionCode) + "_" + currentTime + "_release.type"
    else:
        file_name = project + "_" + str(versionName) + "_" + str(versionCode) + "_" + currentTime + "_release.type"

    if is_test:
        file_name = str(file_name).replace("release", "test")

    if name_suffix == ".apk":
        file_name = str(file_name).replace(".type", ".apk")
    elif name_suffix == ".aab":
        file_name = str(file_name).replace(".type", ".aab")
    elif name_suffix == ".txt":
        file_name = str(file_name).replace(".type", "_mapping.txt")
    else:
        logger.info("未知的文件名后缀：" + str(name_suffix))
        raise Exception("未知的文件名后缀：" + str(name_suffix))

    if is_for32 and is_test == False:
        file_name = file_name.replace("release", "releaseFor32")
    new_name_path = os.path.join(base_dir, file_name)
    logger.info("开始命名文件：{}为：{}".format(file_path, new_name_path))
    os.rename(file_path, new_name_path)
    return new_name_path


def upload_apk(apk_path):
    '''
    上传apk文件
    :param apk_path:apk的路径
    :return: 响应内容，类型：dict
    '''
    _is_exits(apk_path)
    if not str(apk_path).endswith(".apk"):
        raise Exception("文件路径：{}不是apk文件的路径".format(apk_path))

    if str(apk_path).__contains__("test"):
        port = 81
    elif str(apk_path).__contains__("release"):
        port = 82
    else:
        raise Exception("文件路径：{}不是不包含test或者release关键字，请重新命名后才上传".format(apk_path))
    logger.info("开始上传apk文件：" + str(apk_path))
    _, sign_version = get_apksigner_version(apk_path)
    cmd = "curl -X POST " + "\'http://161.117.69.170:" + str(
        port) + "/upload_apk?sign_ver=" + sign_version + "\' -F \"file=@" + apk_path + "\""
    jdata, error = putcmd(cmd)
    try:
        content = json.loads(jdata)
    except:
        raise Exception("上传服务器出错，原因为：\n\n" + str(jdata))
    return content


def upload_file(file_path, is_test):
    '''
    上传非apk文件
    :param file_path: 文件地址
    :param is_test: 是否是测试环境
    :return:响应内容，类型：dict
    '''
    _is_exits(file_path)
    if str(file_path).endswith(".apk"):
        raise Exception("此函数不能上传apk文件，请使用upload_apk函数")
    if is_test:
        url = "http://161.117.69.170:81/upload_file"
    else:
        url = "http://161.117.69.170:82/upload_file"
    files = {'file': open(file_path, 'rb')}
    res = requests.post(url, files=files)
    logger.info("响应内容为：" + res.text)
    return res.json()


def get_version_code(version_name):
    '''
    根据versionName生成版本号
    :param version_name: 版本名
    :return:
    '''
    vcode = version_name.split(".")
    if len(vcode) != 4:
        raise RuntimeError("要求版本号为：1.x.x.x格式")
    vcode1 = vcode[0]
    vcode2 = vcode[1].zfill(2)
    vcode3 = vcode[2].zfill(2)
    vcode4 = vcode[3].zfill(3)
    Bundle_Version_Code = vcode1 + vcode2 + vcode3 + vcode4
    logger.info("生成的versioncode为" + str(Bundle_Version_Code))
    return Bundle_Version_Code


def get_apksigner_version(apk_path):
    '''
     调用apksigner命令解析apk使用哪个版本的签名
     ：param apk_path 具体apk
     ：return：版本，v<版本号>
    '''
    data = _get_variable()
    apksigner_path = data["apksigner_path"]
    cmd = "%s verify --verbose %s" % (apksigner_path, apk_path)
    logger.info("开始执行命令：" + cmd)
    r = os.popen(cmd)
    version = 1
    signer_version = "v1"
    while True:
        text = r.readline()
        if (text == ""):
            break
        text = text.strip()
        if (text.endswith("true")):
            signer_version = text.split(" ")[2]
            version = int(re.findall(r"\d+\.?\d*", text)[0])
    if version > 2:
        version = 2
        signer_version = "v2"
    logger.info("当前的版本签名为：" + str(signer_version))
    return version, signer_version


def modiy_properties_file(path, **kwargs):
    '''
    根据kwargs修改配置文件里面的内容
    :param path: 修改的properties文件路径
    :param kwargs: type:dict,修改的内容。比如：{"a":1},那么path文件以a开头的行将被替换为：a=1
    :return:
    '''
    logger.info("修改{}的内容为：{}".format(path,str(kwargs)))
    keys = kwargs.keys()
    for key in keys:
        for line in fileinput.input(path, inplace=True):
            if line.startswith(key):
                print(key + "=" + kwargs[key])
            else:
                print(line.strip())


def commit_code_before(Branch, gradle_properties_path):
    '''
    提交代码到服务器的前置操作
    :param Branch:当前分支
    :param gradle_properties_path:提交的properties文件路径
    :return: None
    '''
    _is_exits(gradle_properties_path)
    oscmd("git checkout " + gradle_properties_path)
    tagbranch = Branch.replace('origin/', '')
    Checkout_Branch = str(oscmd("git checkout " + tagbranch))
    if Checkout_Branch == "0":
        putcmd("git reset  --hard " + Branch)
        putcmd("git pull")
    else:
        putcmd('git fetch --all && git reset --hard origin/' + tagbranch)
        putcmd("git checkout " + tagbranch)
        putcmd("git pull")


def commit_code_after(Branch, gradle_properties_path, version_name, build_num):
    '''
    提交代码到服务器的后置操作操作
    :param Branch: 当前分支
    :param gradle_properties_path: 提交的properties文件路径
    :param version_name: 版本号
    :param build_num: 构建号
    :return: None
    '''
    _is_exits(gradle_properties_path)
    tagbranch = Branch.replace('origin/', '')
    if build_num is None:
        build_num = 1
        logger.info("build_num为空，取默认值：1")
    if version_name is None:
        raise ProcessExpection("上传代码失败")
    putcmd("git add " + gradle_properties_path)
    putcmd('git commit -am \"android包提交_V' + version_name + '_' + build_num + '\"')
    putcmd('git pull origin ' + tagbranch)
    _, error = putcmd("git push origin " + tagbranch)
    if error:
        code = oscmd("git push origin " + tagbranch)
        if code != 0:
            raise ProcessExpection("上传代码失败")


def add_info_to_cms(is_test, **kwargs):
    '''
    添加信息到cms，参考文档：https://nemo.yuque.com/docs/share/839335c5-66b9-4cb9-b01d-dbc18d5d768c
    :param is_test:是否是测试环境
    :param kwargs:需要增加的内容
    :return:返回响应的结果，type：dict
    '''
    if is_test:
        url = "http://47.74.180.115:8048/api/app-version/add-apk-info"
    else:
        url = "http://cms.flatincbr.com:8000/api/app-version/add-apk-info"
    logger.info("请求的参数为：" + json.dumps(kwargs))
    playload = ''
    for key in kwargs.keys():
        playload += str(key) + "=" + str(kwargs[key]) + "&"
    if playload.endswith("&"):
        playload = playload[:-1]
    logger.info("请求的参数为：" + str(playload))
    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'cache-control': "no-cache",
        'postman-token': "98290854-5b7f-adc4-a3e7-8636e099e2b2"
    }
    response = requests.post(url, data=playload.encode('utf-8'), headers=headers,
                             verify=False, timeout=5)
    logger.info("响应的内容是：" + str(response.text))
    return response.json()


def update_cms_info(is_test, **kwargs):
    '''
    更新信息到cms，参考文档：https://nemo.yuque.com/docs/share/839335c5-66b9-4cb9-b01d-dbc18d5d768c
    :param is_test:是否是测试环境
    :param kwargs:需要更新的内容
    :return:返回响应的结果，type：dict
    '''
    if is_test:
        url = "http://47.74.180.115:8048/api/app-version/update-apk-info"
    else:
        url = "http://cms.flatincbr.com:8000/api/app-version/update-apk-info"

    logger.info("请求的参数为：" + json.dumps(kwargs))
    playload = ''
    for key in kwargs.keys():
        playload += str(key) + "=" + str(kwargs[key]) + "&"
    if playload.endswith("&"):
        playload = playload[:-1]
    logger.info("请求的参数为：" + str(playload))
    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'cache-control': "no-cache",
        'postman-token': "98290854-5b7f-adc4-a3e7-8636e099e2b2"
    }
    response = requests.post(url, data=playload.encode('utf-8'), headers=headers,
                             verify=False, timeout=5)
    logger.info("响应的内容是：" + str(response.text))
    return response.json()


def get_file_md5(file_path):
    """
    获取文件md5值
    :param file_path: 文件路径名
    :return: 文件md5值
    """
    with open(file_path, 'rb') as f:
        md5obj = hashlib.md5()
        md5obj.update(f.read())
        _hash = md5obj.hexdigest()
    return str(_hash)


def reinforce(secret_id,secret_key,oss_url,apk_dir,apk_name):
    '''
    apk加固
    :param oss_url: 首次上传，服务器返回的下载链接
    :param apk_dir: 打出的apk包的路径
    :param apk_name: apk包的名称
    :return:
    '''
    new_apkname = apk_name
    file_path = os.path.join(apk_dir,apk_name)
    md5 = get_file_md5(file_path)
    endpoint = "ms.tencentcloudapi.com"
    Timestamp = int(time.time())
    upload_data = {
        'Action': 'CreateShieldInstance',
        'AppInfo.AppUrl': oss_url,
        'AppInfo.AppMd5': md5,
        'AppInfo.AppSize': '111',
        'ServiceInfo.ServiceEdition': "basic",
        'ServiceInfo.SubmitSource': "MC",
        'ServiceInfo.CallbackUrl': "",
        'Nonce': Timestamp,
        'Region': 'ap-guangzhou',
        'SecretId': secret_id,
        'Timestamp': Timestamp,
        'Version': '2018-04-08'
    }
    s = "GET" + endpoint + "/?" + "&".join("%s=%s" % (k, upload_data[k]) for k in sorted(upload_data))
    upload_data["Signature"] = base64.b64encode(hmac.new(secret_key.encode("utf8"), s.encode("utf8"), hashlib.sha1).digest())
    resp = requests.get("https://" + endpoint, params=upload_data).json()
    itemid = resp['Response']['ItemId']
    get_par = {
        'Action': 'DescribeShieldResult',
        'ItemId': itemid,
        'Nonce': Timestamp,
        'SecretId': secret_id,
        'Timestamp': Timestamp,  #
        'Version': '2018-04-08',
        'Nonce': Timestamp
    }
    s1 = "GET" + endpoint + "/?" + "&".join("%s=%s" % (k, get_par[k]) for k in sorted(get_par))
    get_par['Signature'] = base64.b64encode(hmac.new(secret_key.encode("utf8"), s1.encode("utf8"), hashlib.sha1).digest())
    resp1 = requests.get("https://" + endpoint, params=get_par).json()
    while resp1['Response']['TaskStatus'] == 2:
        logger.info('加固中，请等待...')
        time.sleep(20)
        resp1 = requests.get("https://" + endpoint, params=get_par).json()
    logger.info(resp1['Response']['ShieldInfo']['AppUrl'])
    if resp1['Response']['ShieldInfo']['AppUrl'] == '':
        logger.info('加固失败')
    else:
        r = requests.get(resp1['Response']['ShieldInfo']['AppUrl'])
        new_apk_path = os.path.join(apk_dir,"gu_"+apk_name)
        with open(new_apk_path, "wb") as code:
            code.write(r.content)
        logger.info('加固成功')
        new_apkname = "gu_"+apk_name
    return new_apkname