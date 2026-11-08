# session.sh — Portfolio Risk Lab
# Chạy đầu mỗi buổi bằng:  source session.sh   (KHÔNG chạy bằng bash/sh — biến sẽ mất khi script kết thúc)
# File này commit được: không chứa bí mật.

RISKLAB_BUNDLE="/Volumes/My Passport/RiskLab.sparsebundle"
RISKLAB_MNT="/Volumes/RiskLab"

# 1. Attach RiskLab nếu chưa mount (kiểm tra bằng bảng mount, không chỉ bằng thư mục tồn tại)
if ! mount | grep -q " on ${RISKLAB_MNT} "; then
  if [ ! -d "$RISKLAB_BUNDLE" ]; then
    echo "[LỖI] Không thấy $RISKLAB_BUNDLE — đã cắm WD My Passport chưa?"
    return 1
  fi
  hdiutil attach "$RISKLAB_BUNDLE" || return 1
fi

# 2. Ghi đè biến môi trường cho phiên này (không sửa ~/.zshrc của dự án Hanoi)
export UV_CACHE_DIR="${RISKLAB_MNT}/.uv-cache"
export UV_PYTHON_INSTALL_DIR="${RISKLAB_MNT}/.uv-python"
export RISKLAB_DATA="${RISKLAB_MNT}/risklab-data"

# 3. Vào repo
cd "${RISKLAB_MNT}/portfolio-risk-lab" || return 1

# 4. In trạng thái
echo "UV_CACHE_DIR=$UV_CACHE_DIR"
echo "UV_PYTHON_INSTALL_DIR=$UV_PYTHON_INSTALL_DIR"
echo "RISKLAB_DATA=$RISKLAB_DATA"
df -h "$RISKLAB_MNT" "/Volumes/My Passport"
