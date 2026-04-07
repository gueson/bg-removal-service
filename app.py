"""
Background Removal Service
使用 u2net 或 rembg 进行背景去除
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import os
import base64
from datetime import datetime

# 背景去除库
try:
    from rembg import remove, new_session
    from PIL import Image
    REMBG_AVAILABLE = True
    # 使用 bria-rmbg 模型，比 u2net 更好地保留前景内容
    REMBG_SESSION = new_session('bria-rmbg')
except ImportError:
    REMBG_AVAILABLE = False
    REMBG_SESSION = None

app = FastAPI(title="Background Removal Service")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "rembg_available": REMBG_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.post("/process")
async def process_image(file: UploadFile = File(...)):
    """
    处理图片，去除背景
    """
    if not REMBG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Background removal library not available"
        )
    
    # 验证文件类型
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # 创建临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as input_tmp:
        content = await file.read()
        input_tmp.write(content)
        input_path = input_tmp.name
    
    try:
        # 打开图片
        input_image = Image.open(input_path)
        
        # 去除背景，使用 bria-rmbg 模型 + alpha_matting 提升质量和前景保留
        output_image = remove(
            input_image,
            session=REMBG_SESSION,
            alpha_matting=True,
            alpha_matting_foreground_threshold=230,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=5,
            post_process_mask=True,
        )
        
        # 保存结果
        output_path = input_path.replace(os.path.splitext(file.filename)[1], "_transparent.png")
        output_image.save(output_path, "PNG")
        
        # 读取结果
        with open(output_path, "rb") as f:
            result_data = f.read()
        
        return {
            "result_url": f"data:image/png;base64,{base64.b64encode(result_data).decode('utf-8')}",
            "original_size": len(content),
            "result_size": len(result_data),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
        
    finally:
        # 清理临时文件
        if os.path.exists(input_path):
            os.unlink(input_path)
        if 'output_path' in locals() and os.path.exists(output_path):
            os.unlink(output_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
