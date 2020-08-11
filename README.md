## 技术栈

- 后端：Flask
- 数据库：MySQL + Flask-SQLAlchemy
- 登陆管理：authentication + jwt 权限验证

## 项目结构

- model_svr：用户管理后台

## 进展&TODO

- [x] 后端管理后台建立，数据库建表
- [ ]  原型图接口对齐
- [ ]  前后端联调

## 数据库
- Users表：注册医生的姓名，密码，权限等信息
- Patients表：存储患者拥有的CT图像，拥有他的医生
- CTImgs表：存储img信息
- Results表：存储图像分析结果
- models表：存储模型信息

#### 运行方法：python app.py 安装好所有环境后即可运行。

