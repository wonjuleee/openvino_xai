# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import csv
import os
import shutil
from pathlib import Path

import cv2
import numpy as np
import openvino as ov
import pytest

from openvino_xai.common.parameters import Method, Task
from openvino_xai.explainer.explainer import Explainer, ExplainMode
from openvino_xai.explainer.utils import (
    ActivationType,
    get_postprocess_fn,
    get_preprocess_fn,
    get_score,
)
from openvino_xai.explainer.visualizer import Visualizer
from openvino_xai.utils.model_export import export_to_ir, export_to_onnx

timm = pytest.importorskip("timm")
torch = pytest.importorskip("torch")
pytest.importorskip("onnx")


TEST_MODELS = timm.list_models(pretrained=True)

CNN_MODELS = [
    "bat_resnext",
    "convnext",
    "cs3",
    "cs3darknet",
    "darknet",
    "densenet",
    "dla",
    "dpn",
    "efficientnet",
    "ese_vovnet",
    "fbnet",
    "gernet",
    "ghostnet",
    "hardcorenas",
    "hrnet",
    "inception",
    "lcnet",
    "legacy_",
    "mixnet",
    "mnasnet",
    "mobilenet",
    "nasnet",
    "regnet",
    "repvgg",
    "res2net",
    "res2next",
    "resnest",
    "resnet",
    "resnext",
    "rexnet",
    "selecsls",
    "semnasnet",
    "senet",
    "seresnext",
    "spnasnet",
    "tinynet",
    "tresnet",
    "vgg",
    "xception",
]

SUPPORTED_BUT_FAILED_BY_BB_MODELS = {}

NOT_SUPPORTED_BY_BB_MODELS = {
    "_nfnet_": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "convit": "RuntimeError: Couldn't get TorchScript module by tracing.",
    "convnext_xxlarge": "RuntimeError: The serialized model is larger than the 2GiB limit imposed by the protobuf library.",
    "convnextv2_huge": "RuntimeError: The serialized model is larger than the 2GiB limit imposed by the protobuf library.",
    "deit3_huge": "RuntimeError: The serialized model is larger than the 2GiB limit imposed by the protobuf library.",
    "dm_nfnet": "openvino._pyopenvino.GeneralFailure: Check 'false' failed at src/frontends/onnx/frontend/src/frontend.cpp:144",
    "eca_nfnet": "openvino._pyopenvino.GeneralFailure: Check 'false' failed at src/frontends/onnx/frontend/src/frontend.cpp:144",
    "eva_giant": "RuntimeError: The serialized model is larger than the 2GiB limit imposed by the protobuf library.",
    "halo": "torch.onnx.errors.SymbolicValueError: Unsupported: ONNX export of operator Unfold, input size not accessible.",
    "nf_regnet": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "nf_resnet": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "nfnet_l0": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "regnety_1280": "RuntimeError: The serialized model is larger than the 2GiB limit imposed by the protobuf library.",
    "regnety_2560": "RuntimeError: The serialized model is larger than the 2GiB limit imposed by the protobuf library.",
    "repvit": "urllib.error.HTTPError: HTTP Error 404: Not Found",
    "resnetv2": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "tf_efficientnet_cc": "torch.onnx.errors.SymbolicValueError: Unsupported: ONNX export of convolution for kernel of unknown shape.",
    "vit_base_r50_s16_224.orig_in21k": "RuntimeError: Error(s) in loading state_dict for VisionTransformer",
    "vit_gigantic_patch16_224_ijepa.in22k": "RuntimeError: shape '[1, 13, 13, -1]' is invalid for input of size 274560",
    "vit_huge_patch14_224.orig_in21k": "RuntimeError: Error(s) in loading state_dict for VisionTransformer",
    "vit_large_patch32_224.orig_in21k": "RuntimeError: Error(s) in loading state_dict for VisionTransformer",
    "vit_large_r50_s32": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "vit_small_r26_s32": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "vit_tiny_r_s16": "RuntimeError: Exception from src/inference/src/cpp/core.cpp:90: Training mode of BatchNormalization is not supported.",
    "volo_": "torch.onnx.errors.UnsupportedOperatorError: Exporting the operator 'aten::col2im' to ONNX opset version 14 is not supported.",
}

SUPPORTED_BUT_FAILED_BY_WB_MODELS = {
    "convformer": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "swin": "Only two outputs of the between block Add node supported, but got 1. Try to use black-box.",
}

NOT_SUPPORTED_BY_WB_MODELS = {
    **NOT_SUPPORTED_BY_BB_MODELS,
    # Killed on WB
    "beit_large_patch16_512": "Failed to allocate 94652825600 bytes of memory",
    "eva_large_patch14_336": "OOM Killed",
    "eva02_base_patch14_448": "OOM Killed",
    "eva02_large_patch14_448": "OOM Killed",
    "mobilevit_": "Segmentation fault",
    "mobilevit_xxs": "Segmentation fault",
    "mvitv2_base.fb_in1k": "Segmentation fault",
    "mvitv2_large": "OOM Killed",
    "mvitv2_small": "Segmentation fault",
    "mvitv2_tiny": "Segmentation fault",
    "pit_": "Segmentation fault",
    "pvt_": "Segmentation fault",
    "tf_efficientnet_l2.ns_jft_in1k": "OOM Killed",
    "xcit_large": "Failed to allocate 81581875200 bytes of memory",
    "xcit_medium_24_p8_384": "OOM Killed",
    "xcit_small_12_p8_384": "OOM Killed",
    "xcit_small_24_p8_384": "OOM Killed",
    # Not expected to work for now
    "botnet26t_256": "Only two outputs of the between block Add node supported, but got 1",
    "caformer": "One (and only one) of the nodes has to be Add type. But got MVN and Multiply.",
    "cait_": "Cannot create an empty Constant. Please provide valid data.",
    "coat_": "Only two outputs of the between block Add node supported, but got 1.",
    "coatn": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "convmixer": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "crossvit": "One (and only one) of the nodes has to be Add type. But got StridedSlice and StridedSlice.",
    "davit": "Only two outputs of the between block Add node supported, but got 1.",
    "eca_botnext": "Only two outputs of the between block Add node supported, but got 1.",
    "edgenext": "Only two outputs of the between block Add node supported, but got 1",
    "efficientformer": "Cannot find output backbone_node in auto mode.",
    "focalnet": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "gcvit": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "levit_": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "maxvit": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "maxxvit": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "mobilevitv2": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "nest_": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "poolformer": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "sebotnet": "Only two outputs of the between block Add node supported, but got 1.",
    "sequencer2d": "Cannot find output backbone_node in auto mode, please provide target_layer.",
    "tnt_s_patch16_224": "Only two outputs of the between block Add node supported, but got 1.",
    "tresnet": "Batch shape of the output should be dynamic, but it is static.",
    "twins": "One (and only one) of the nodes has to be Add type. But got ShapeOf and Transpose.",
    "visformer": "Cannot find output backbone_node in auto mode, please provide target_layer",
    "vit_relpos_base_patch32_plus_rpn_256": "Check 'TRShape::merge_into(output_shape, in_copy)' failed",
    "vit_relpos_medium_patch16_rpn_224": "ValueError in openvino_xai/methods/white_box/recipro_cam.py:215",
}


class TestImageClassificationTimm:
    clear_cache_converted_models = False
    clear_cache_hf_models = False
    supported_num_classes = {
        1000: 293,  # 293 is a cheetah class_id in the ImageNet-1k dataset
        21841: 2441,  # 2441 is a cheetah class_id in the ImageNet-21k dataset
        21843: 2441,  # 2441 is a cheetah class_id in the ImageNet-21k dataset
        11821: 1652,  # 1652 is a cheetah class_id in the ImageNet-12k dataset
    }

    @pytest.fixture(autouse=True)
    def setup(self, fxt_data_root, fxt_output_root, fxt_clear_cache):
        self.data_dir = fxt_data_root
        self.output_dir = fxt_output_root
        self.clear_cache_hf_models = fxt_clear_cache
        self.clear_cache_converted_models = fxt_clear_cache

    @pytest.mark.parametrize("model_id", TEST_MODELS)
    def test_classification_white_box(self, model_id, dump_maps=False):
        for skipped_model in NOT_SUPPORTED_BY_WB_MODELS.keys():
            if skipped_model in model_id:
                pytest.skip(reason=NOT_SUPPORTED_BY_WB_MODELS[skipped_model])

        for failed_model in SUPPORTED_BUT_FAILED_BY_WB_MODELS.keys():
            if failed_model in model_id:
                pytest.xfail(reason=SUPPORTED_BUT_FAILED_BY_WB_MODELS[failed_model])

        explain_method = Method.VITRECIPROCAM
        for cnn_model in CNN_MODELS:
            if cnn_model in model_id:
                explain_method = Method.RECIPROCAM
                break

        timm_model, model_cfg = self.get_timm_model(model_id)
        input_size = list(timm_model.default_cfg["input_size"])
        dummy_tensor = torch.rand([1] + input_size)
        model = ov.convert_model(timm_model, example_input=dummy_tensor, input=(ov.PartialShape([-1] + input_size),))

        mean_values = [(item * 255) for item in model_cfg["mean"]]
        scale_values = [(item * 255) for item in model_cfg["std"]]
        preprocess_fn = get_preprocess_fn(
            change_channel_order=True,
            input_size=model_cfg["input_size"][1:],
            mean=mean_values,
            std=scale_values,
            hwc_to_chw=True,
        )

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=preprocess_fn,
            explain_mode=ExplainMode.WHITEBOX,  # defaults to AUTO
            explain_method=explain_method,
            embed_scaling=False,
        )

        target_class = self.supported_num_classes[model_cfg["num_classes"]]
        image = cv2.imread("tests/assets/cheetah_person.jpg")
        explanation = explainer(
            image,
            targets=[target_class],
            resize=False,
            colormap=False,
        )

        assert explanation is not None
        assert explanation.shape[-1] > 1 and explanation.shape[-2] > 1
        print(f"{model_id}: Generated classification saliency maps with shape {explanation.shape}.")
        self.clear_cache()

    @pytest.mark.parametrize("model_id", TEST_MODELS)
    def test_classification_black_box(self, model_id, dump_maps=False):
        for skipped_model in NOT_SUPPORTED_BY_BB_MODELS.keys():
            if skipped_model in model_id:
                pytest.skip(reason=NOT_SUPPORTED_BY_BB_MODELS[skipped_model])

        for failed_model in SUPPORTED_BUT_FAILED_BY_BB_MODELS.keys():
            if failed_model in model_id:
                pytest.xfail(reason=SUPPORTED_BUT_FAILED_BY_BB_MODELS[failed_model])

        timm_model, model_cfg = self.get_timm_model(model_id)
        input_size = list(timm_model.default_cfg["input_size"])
        dummy_tensor = torch.rand([1] + input_size)
        model = ov.convert_model(timm_model, example_input=dummy_tensor, input=(ov.PartialShape([-1] + input_size),))

        mean_values = [(item * 255) for item in model_cfg["mean"]]
        scale_values = [(item * 255) for item in model_cfg["std"]]
        preprocess_fn = get_preprocess_fn(
            change_channel_order=True,
            input_size=model_cfg["input_size"][1:],
            mean=mean_values,
            std=scale_values,
            hwc_to_chw=True,
        )

        postprocess_fn = get_postprocess_fn()

        explainer = Explainer(
            model=model,
            task=Task.CLASSIFICATION,
            preprocess_fn=preprocess_fn,
            postprocess_fn=postprocess_fn,
            explain_mode=ExplainMode.BLACKBOX,  # defaults to AUTO
        )

        image = cv2.imread("tests/assets/cheetah_person.jpg")
        target_class = self.supported_num_classes[model_cfg["num_classes"]]
        explanation = explainer(
            image,
            targets=[target_class],
            # num_masks=2000,  # kwargs of the RISE algo
            num_masks=2,  # minimal iterations for feature test
        )

        assert explanation is not None
        assert explanation.shape[-1] > 1 and explanation.shape[-2] > 1
        print(f"{model_id}: Generated classification saliency maps with shape {explanation.shape}.")
        self.clear_cache()

    def get_timm_model(self, model_id):
        timm_model = timm.create_model(model_id, in_chans=3, pretrained=True, checkpoint_path="")
        timm_model.eval()
        model_cfg = timm_model.default_cfg
        num_classes = model_cfg["num_classes"]
        if num_classes not in self.supported_num_classes:
            self.clear_cache()
            pytest.skip(f"Number of model classes {num_classes} unknown")
        return timm_model, model_cfg

    def clear_cache(self):
        if self.clear_cache_converted_models:
            ir_model_dir = self.output_dir / "timm_models" / "converted_models"
            if ir_model_dir.is_dir():
                shutil.rmtree(ir_model_dir)
        if self.clear_cache_hf_models:
            cache_dir = os.environ.get("XDG_CACHE_HOME", "~/.cache")
            huggingface_hub_dir = Path(cache_dir) / "huggingface/hub/"
            if huggingface_hub_dir.is_dir():
                shutil.rmtree(huggingface_hub_dir)
