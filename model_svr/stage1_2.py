import nibabel as nib
import numpy as np
import joblib
import torch
from torchvision import transforms
import models
from skimage import transform as sktrans

normalize = transforms.Compose([
    transforms.ToTensor(),
])


def stage1_init():
    perf_model = models.Unet_Non_local(drop_rate=0.4, bn_momentum=0.1)
    perf_model.load_state_dict(
        torch.load('model/perf_unet.pth.tar', map_location='cpu')['state_dict'])
    # perf_model.cuda()
    perf_model.eval()

    nonperf_model = models.Unet_Non_local(drop_rate=0.4, bn_momentum=0.1)
    nonperf_model.load_state_dict(
        torch.load('model/nonperf_unet.pth.tar', map_location='cpu')['state_dict'])
    # nonperf_model.cuda()
    nonperf_model.eval()
    return perf_model, nonperf_model

def stage2_init():
    perf_clf = joblib.load("model/perf_rf_3.pkl")
    nonperf_clf = joblib.load("model/nonperf_rf_3.pkl")
    return perf_clf, nonperf_clf


def load_imgs(adc_path, dwi_path):
    res = {}
    if adc_path:
        adc = nib.load(adc_path)
        adc_arr = adc.get_fdata()
        adc_arr = np.squeeze(adc_arr)
        res['adc'] = adc_arr
    if dwi_path:
        dwi = nib.load(dwi_path)
        dwi_arr = dwi.get_fdata()
        dwi_arr = np.squeeze(dwi_arr)
        res['dwi'] = dwi_arr
        res['affine'] = dwi.affine
    return res


def _stage1(perf_model, nonperf_model, dwi_arr, adc_arr, socketio):
    perf_preds = []
    nonperf_preds = []
    with torch.no_grad():
        for i in range(dwi_arr.shape[2]):
            socketio.emit("process", "{}".format((i+1)/dwi_arr.shape[2]*50))
            dwi_ori_img = dwi_arr[:, :, i]
            adc_ori_img = adc_arr[:, :, i]

            dwi_ori_img = np.clip(dwi_ori_img,0,5000)/5000.
            adc_ori_img = (np.clip(adc_ori_img, -0.004, 0.008) + 0.004) / 0.012
            h,w = dwi_ori_img.shape
            ori_img = np.stack([dwi_ori_img, adc_ori_img], axis=2)
            ori_img = ori_img.astype(np.float32)
            img = sktrans.resize(ori_img, (224,224))
            img = normalize(img)

            img = img.unsqueeze(0)
            perf_out = perf_model(img)
            nonperf_out = nonperf_model(img)
            perf_out[perf_out >= 0.5] = 1.0
            perf_out[perf_out < 0.5] = 0
            perf_out = perf_out.cpu().numpy()[0,0]
            perf_out = perf_out.astype(np.float32)
            perf_preds.append(sktrans.resize(perf_out, (w,h)))

            nonperf_out[nonperf_out >= 0.5] = 1.0
            nonperf_out[nonperf_out < 0.5] = 0
            nonperf_out = nonperf_out.cpu().numpy()[0,0]
            nonperf_out = nonperf_out.astype(np.float32)
            nonperf_preds.append(sktrans.resize(nonperf_out, (w,h)))
    return np.stack(perf_preds, axis=2), np.stack(nonperf_preds, axis=2)


def get_value(data, x, y, z):
    w,h,d = data.shape
    if x<0 or y<0 or z<0 or x>=w or y>=h or z>=d:
        return 0
    else:
        return data[x,y,z]


def get_line(data1, data2, x,y,z,r=3):
    res1 = []
    res2 = []
    for i in range(-1,2):
        for j in range(-1,2):
            for k in range(-1,2):
                res1.append(get_value(data1, x+i, y+j, z+k))
                res2.append(get_value(data2, x+i, y+j, z+k))
    res1.extend(res2)
    return res1


def stage2_prepare(adc_arr, dwi_arr, idx):
    inp = []
    inp_idx = []
    for x in range(dwi_arr.shape[0]):
        for y in range(dwi_arr.shape[1]):
            if dwi_arr[x, y, idx] > 1000:
                inp.append(get_line(dwi_arr, adc_arr, x, y, idx))
                inp_idx.append((x, y))
    return inp, inp_idx

def _stage2(clf, inp, thresh):
    if inp:
        pred = clf.predict_proba(np.stack(inp))[:, 1]
        pred[pred>=thresh]=1
        pred[pred<thresh]=0
    else:
        pred = None
    return pred


def stage2(perf_model, nonperf_model, perf_clf, nonperf_clf, dwi_arr, adc_arr, socketio):
    perf_ress = []
    nonperf_ress = []
    for idx in range(dwi_arr.shape[2]):
        socketio.emit("process", "{}".format((idx+1)/ dwi_arr.shape[2] * 100))
        inp, inp_idx = stage2_prepare(adc_arr, dwi_arr, idx=idx)
        stage2_perf_pred = _stage2(perf_clf, inp, thresh=0.3)
        stage2_nonperf_pred = _stage2(nonperf_clf, inp, thresh=0.3)
        perf_res = np.zeros((dwi_arr.shape[0], dwi_arr.shape[1]))
        nonperf_res = np.zeros((dwi_arr.shape[0], dwi_arr.shape[1]))
        if inp:
            for ii, (x, y) in enumerate(inp_idx):
                perf_res[x, y] = stage2_perf_pred[ii]
                nonperf_res[x, y] = stage2_nonperf_pred[ii]
        perf_ress.append(perf_res)
        nonperf_ress.append(nonperf_res)
    perf_ress = np.stack(perf_ress, axis=2)
    nonperf_ress = np.stack(nonperf_ress, axis=2)
    socketio.emit("process", "分析已完成！")
    return perf_ress, nonperf_ress, max(0,np.sum(nonperf_ress)/np.sum(perf_ress)*100-100)


def stage1_2(perf_model, nonperf_model, perf_clf, nonperf_clf, dwi_arr, adc_arr, socketio):
    perf_preds1, nonperf_preds1 = _stage1(perf_model, nonperf_model, dwi_arr, adc_arr, socketio)
    perf_ress = []
    nonperf_ress = []
    for idx in range(dwi_arr.shape[2]):
        socketio.emit("process", "{}".format((idx+1)/ dwi_arr.shape[2] * 50+50))
        inp, inp_idx = stage2_prepare(adc_arr, dwi_arr, idx=idx)
        stage2_perf_pred = _stage2(perf_clf, inp, thresh=0.3)
        stage2_nonperf_pred = _stage2(nonperf_clf, inp, thresh=0.3)
        perf_res = np.zeros((dwi_arr.shape[0], dwi_arr.shape[1]))
        nonperf_res = np.zeros((dwi_arr.shape[0], dwi_arr.shape[1]))
        if inp:
            for ii, (x, y) in enumerate(inp_idx):
                perf_res[x, y] = stage2_perf_pred[ii]
                nonperf_res[x, y] = stage2_nonperf_pred[ii]
        perf_res = perf_res*perf_preds1[:,:,idx]
        nonperf_res = nonperf_res*nonperf_preds1[:,:,idx]
        perf_ress.append(perf_res)
        nonperf_ress.append(nonperf_res)
    perf_ress = np.stack(perf_ress, axis=2)
    nonperf_ress = np.stack(nonperf_ress, axis=2)
    socketio.emit("process", "分析已完成！")
    return perf_ress, nonperf_ress, max(0,np.sum(nonperf_ress>0.2)/np.sum(perf_ress>0.2)*100-100)


def to_nii(data, affine):
    img = nib.Nifti1Image(data, affine=affine)
    return img
