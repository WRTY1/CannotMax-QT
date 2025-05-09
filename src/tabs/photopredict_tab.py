from src.utils import get_config, get_spinbox_column_data, select_roi
from src.thread import NNWorker, NNThread
from src.recognize import recognize_monsters
import os
import torch
from .base_tab import BaseTab
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QTableWidget, 
                              QHeaderView, QSpinBox, QHBoxLayout, QLabel, QWidget, 
                              QVBoxLayout,QTableWidgetItem, QMessageBox)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QPixmap, QImage, QGuiApplication
from PySide6.QtCore import Slot, Qt
import numpy as np
from PIL import ImageGrab
from PySide6.QtGui import QImage

class PhotoPredictTab(BaseTab):

    UI_NAME = 'photopredict_tab'
    def setup_ui(self):
        
        self.config = get_config()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = self.config["model_dir"]

        layout = QVBoxLayout(self)
        layout.addWidget(self.ui)
        self.setLayout(layout)
        
        self._init_nn_thread()
        self.clear_tables()
        self._init_enemy_selection_table()
        
    def setup_connections(self):
        # 初始化连接
        self._load_files()
        self.ui.comboSelectModel.currentTextChanged.connect(self._update_model)
        self.ui.btnClear.clicked.connect(self._clear_all_numbers)
        self.ui.btnCheck.clicked.connect(self._transfer_valid_data)
        
        # 截图按钮连接
        self.ui.btnCapture.clicked.connect(self._on_area_capture)
        
        # 初始化UI状态
        self._set_capture_ui_state(False, "点击按钮开始选区截图")

    def _set_capture_ui_state(self, capturing, message=None):
        """设置截图UI状态"""
        self.ui.btnCapture.setEnabled(not capturing)
        if hasattr(self.ui, 'labelCaptureStatus'):  # 如果有状态标签
            self.ui.labelCaptureStatus.setText(message if message else "")
        
        # 设置忙碌光标
        QGuiApplication.setOverrideCursor(
            Qt.CrossCursor if capturing else Qt.ArrowCursor
        )
        if not capturing:
            QGuiApplication.restoreOverrideCursor()

    @Slot()
    def _on_area_capture(self):
        """区域截图功能"""
        try:
            self._set_capture_ui_state(True, "请拖动鼠标选择区域 (ESC取消)")
            
            # 使用改进的OpenCV选区
            roi = select_roi()
            
            if not roi:  # 用户取消选择
                self._set_capture_ui_state(False, "选区已取消")
                return
            
            print(roi)
            # 获取选区截图并确保内存连续
            (x1, y1), (x2, y2) = roi
            
            screenshot = ImageGrab.grab()
            cropped = screenshot.crop((x1, y1, x2, y2)).convert("RGB")
            

            # 获取当前文件的上上级路径 + tmp 文件夹
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            tmp_dir = os.path.join(project_root, "tmp")
            os.makedirs(tmp_dir, exist_ok=True)


            filepath = os.path.join(tmp_dir, "screenshot.png")
            cropped.save(filepath)

            # 从文件中加载 QImage
            q_img = QImage(filepath)
            if q_img.isNull():
                raise RuntimeError("QImage 从 PNG 文件加载失败")

            # 显示
            pixmap = QPixmap.fromImage(q_img)
            self.ui.labelScreenshot.setPixmap(
                pixmap.scaled(
                    self.ui.labelScreenshot.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
            
            
            # 识别处理
            enemy_list = recognize_monsters(pixmap)
            self._update_table(enemy_list)
            self._set_capture_ui_state(False, "识别完成！点击按钮重新截图")
            
        except Exception as e:
            self._show_error(f"截图失败: {str(e)}")
            import traceback
            traceback.print_exc()  # 打印完整错误堆栈
        finally:
            self._set_capture_ui_state(False)

    def _show_error(self, error_msg):
        """显示错误信息"""
        self.ui.labelScreenshot.setText("截图错误")
        if hasattr(self.ui, 'labelCaptureStatus'):
            self.ui.labelCaptureStatus.setText(error_msg)
        
        QMessageBox.critical(
            self,
            "截图错误",
            error_msg,
            QMessageBox.Ok
        )


    def _update_table(self, enemy_list):
        pass



    def _load_files(self):
        """加载指定目录下的所有文件名到下拉栏"""
        directory = self.config["save_dir"]  # 替换成你的目标文件夹路径
        self.ui.comboSelectModel.clear()  # 清空现有选项

        try:
            files = os.listdir(directory)
            for file in files:
                if os.path.isfile(os.path.join(directory, file)):  # 只添加文件，不包含子目录
                    self.ui.comboSelectModel.addItem(file)
        except FileNotFoundError:
            print(f"错误: 目录 '{directory}' 不存在！")

    def _update_model(self, model):
        self.model = os.path.join(self.config["save_dir"], model)
        self._init_nn_thread() 

    def clear_tables(self):
        """清空所有表格数据"""
        tables = [
            self.ui.tableSelectEnemy,
            self.ui.tableDispLeft,
            self.ui.tableDispRight
        ]
        for table in tables:
            table.setRowCount(0)
            table.clearContents()
        
    def _init_enemy_selection_table(self):
        for table in [self.ui.tableDispLeft, self.ui.tableDispRight]:
            table.setColumnCount(2)
            table.setHorizontalHeaderLabels(["敌人", "数量"])
            table.setColumnWidth(0, 80)
            table.setColumnWidth(1, 60)
            
        """初始化敌人选择表格（自适应行高+大图显示）"""
        table = self.ui.tableSelectEnemy
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["敌人", "左数量", "右数量"])
        
        # 设置列宽策略
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 图片列自适应
        header.setSectionResizeMode(1, QHeaderView.Fixed)    # 固定宽度
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(1, 60)  # 加宽数值输入列
        header.resizeSection(2, 60)

        # 禁用默认行高设置，启用内容自适应
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        # 图片目录路径
        image_dir = self.config['ui_photos_direc']
        
        try:
            # 获取并排序PNG文件
            png_files = sorted(
                [f for f in os.listdir(image_dir) if f.lower().endswith('.png')],
                key=lambda x: int(os.path.splitext(x)[0])
            )
            
            for row, filename in enumerate(png_files):
                table.insertRow(row)
                
                # 第一列：图片显示（带悬停提示）
                cell_widget = QWidget()
                layout = QHBoxLayout(cell_widget)
                layout.setContentsMargins(2,2,2,2)  # 增加垂直边距
                layout.setAlignment(Qt.AlignCenter)
                
                # 图片标签（放大显示）
                icon_label = QLabel()
                pixmap = QPixmap(os.path.join(image_dir, filename))
                if not pixmap.isNull():
                    # 设置大尺寸显示（保留原始比例）
                    scaled_pixmap = pixmap.scaledToHeight(
                        52,  # 固定高度，宽度按比例自动计算
                        Qt.SmoothTransformation
                    )
                    icon_label.setPixmap(scaled_pixmap)
                    icon_label.setToolTip(f"ID: {os.path.splitext(filename)[0]}")
                
                layout.addWidget(icon_label)
                table.setCellWidget(row, 0, cell_widget)
                
                # 数值输入列
                spin_left = QSpinBox()
                spin_left.setRange(0, 999)
                spin_left.setAlignment(Qt.AlignCenter)
                table.setCellWidget(row, 1, spin_left)
                
                spin_right = QSpinBox()
                spin_right.setRange(0, 999)
                spin_right.setAlignment(Qt.AlignCenter)
                table.setCellWidget(row, 2, spin_right)
                
                # 设置该行最小高度（根据图片实际高度+边距）
                table.setRowHeight(row, scaled_pixmap.height())
                
        except Exception as e:
            print(f"加载敌人图片失败: {e}")

    def _clear_all_numbers(self):
        """清空所有数量输入框（btnClear功能）"""
        table = self.ui.tableSelectEnemy
        for row in range(table.rowCount()):
            # 获取左数量输入框
            spin_left = table.cellWidget(row, 1)
            if isinstance(spin_left, QSpinBox):
                spin_left.setValue(0)
            
            # 获取右数量输入框
            spin_right = table.cellWidget(row, 2)
            if isinstance(spin_right, QSpinBox):
                spin_right.setValue(0)
    
    def _transfer_valid_data(self):
        """修复版：稳定处理多行数据转移"""
        src_table = self.ui.tableSelectEnemy
        left_table = self.ui.tableDispLeft
        right_table = self.ui.tableDispRight
        
        # 清空目标表格时保留列设置
        left_table.clearContents()
        right_table.clearContents()
        left_table.setRowCount(0)
        right_table.setRowCount(0)
        
        # 强制立即应用表格样式
        self._force_table_style(left_table)
        self._force_table_style(right_table)
        
        # 遍历源表格
        for src_row in range(src_table.rowCount()):
            img_widget = src_table.cellWidget(src_row, 0)
            spin_left = src_table.cellWidget(src_row, 1)
            spin_right = src_table.cellWidget(src_row, 2)
            
            if not all([img_widget, spin_left, spin_right]):
                continue
                
            left_val = spin_left.value()
            right_val = spin_right.value()
            pixmap = img_widget.findChild(QLabel).pixmap()
            
            # 左数量处理
            if left_val > 0:
                left_row = left_table.rowCount()
                left_table.insertRow(left_row)
                
                # 图片单元格（固定高度）
                left_img_cell = self._create_image_cell(pixmap, target_height=52)
                left_table.setCellWidget(left_row, 0, left_img_cell)
                
                # SpinBox单元格
                left_spin_cell = self._create_spinbox(left_val)
                left_table.setCellWidget(left_row, 1, left_spin_cell)
                
                # 显式设置行高
                left_table.setRowHeight(left_row, left_img_cell.sizeHint().height())

            # 右数量处理（相同逻辑）
            if right_val > 0:
                right_row = right_table.rowCount()
                right_table.insertRow(right_row)
                
                right_img_cell = self._create_image_cell(pixmap, target_height=52)
                right_table.setCellWidget(right_row, 0, right_img_cell)
                
                right_spin_cell = self._create_spinbox(right_val)
                right_table.setCellWidget(right_row, 1, right_spin_cell)
                
                right_table.setRowHeight(right_row, right_img_cell.sizeHint().height())

        self._predict_result()


    def _force_table_style(self, table):
        """强制刷新表格样式"""
        table.style().unpolish(table)
        table.style().polish(table)
        table.updateGeometry()
        table.viewport().update()

    def _create_image_cell(self, pixmap, target_height):
        """创建标准化图片单元格（带高度控制）"""
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(2,2,2,2)
        
        label = QLabel()
        scaled_pix = pixmap.scaledToHeight(
            target_height - 2,  # 减去边距
            Qt.SmoothTransformation
        )
        label.setPixmap(scaled_pix)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        # 固定单元格最小尺寸
        cell.setMinimumSize(scaled_pix.width() , target_height)
        return cell

    def _create_spinbox(self, value):
        """创建标准化SpinBox"""
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignCenter)
        spin.setReadOnly(True)

        return spin

    def _init_nn_thread(self):
        if hasattr(self, '_nn_thread') and self._nn_thread.isRunning():
            self._nn_thread.safe_stop()  # 自定义的安全停止方法
        self._nn_thread = NNThread(model_path = self.model)
        self._nn_thread.worker.prediction_ready.connect(self._handle_prediction)
        self._nn_thread.worker.error_occurred.connect(self._handle_error)
        self._nn_thread.start()



    def predictText(self, prediction):
        """格式化预测结果并设置样式（完全匹配原始逻辑）"""
        # 确保预测值在合理范围内
        prediction = max(0.0, min(1.0, prediction))
        
        # 计算双方胜率
        right_win_prob = prediction  # 模型输出的是右方胜率
        left_win_prob = 1 - right_win_prob

        # 格式化输出文本（保持完全一致）
        result_text = (f"预测结果:\n"
                    f"左方胜率: {left_win_prob:.2%}\n"
                    f"右方胜率: {right_win_prob:.2%}")

        # 根据胜率设置颜色和字体（完全复制原始逻辑）
        if left_win_prob > 0.7:
            color = "#E23F25"  # 红色
            font_weight = "bold"
        elif left_win_prob > 0.6:
            color = "#E23F25"  # 红色 
            font_weight = "bold"
        elif right_win_prob > 0.7:
            color = "#25ace2"  # 蓝色
            font_weight = "bold"
        elif right_win_prob > 0.6:
            color = "#25ace2"  # 蓝色
            font_weight = "bold"
        else:
            color = "#000000"  # 黑色
            font_weight = "bold"

        # 应用样式到QPlainTextEdit（实现等效于Tkinter的config）
        self.ui.textOutcome.setPlainText(result_text)
        self.ui.textOutcome.setStyleSheet(f"""
            QPlainTextEdit {{
                color: {color};
                font-weight: {font_weight};
                font-size: 12pt;
                font-family: Helvetica;
            }}
        """)
    
        return result_text

    def _predict_result(self):
        try:
            left_counts = get_spinbox_column_data(self.ui.tableSelectEnemy, 1)
            right_counts = get_spinbox_column_data(self.ui.tableSelectEnemy, 2)

            self.ui.textOutcome.setPlainText("计算中...")
            self._nn_thread.request_prediction(left_counts, right_counts)

        except Exception as e:
            self.ui.textOutcome.setPlainText(f"错误: {str(e)}")

    
    def _handle_prediction(self, prediction):
        """处理预测结果信号"""
        self.predictText(prediction)  # 自动更新UI

    def _handle_error(self, error_msg):
        """处理错误信号"""
        self.ui.textOutcome.setPlainText(error_msg)
       
    def cleanup(self):
        """清理资源，关闭线程"""
        if hasattr(self, '_nn_thread'):
            self._nn_thread.quit()  # 请求线程退出
            self._nn_thread.wait()  # 等待线程结束
            del self._nn_thread


