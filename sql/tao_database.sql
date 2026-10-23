-- Tạo database và các bảng cho web Dự báo tỷ giá USD/VND.
-- Có thể chạy file này trực tiếp trong VS Code (chuột phải kết nối > New Query > dán > Ctrl+Shift+E)
-- hoặc chạy "python khoi_tao_db.py". Chạy lại nhiều lần cũng không sao.

IF DB_ID(N'DuBaoTyGia') IS NULL
    CREATE DATABASE DuBaoTyGia;
GO

USE DuBaoTyGia;
GO

-- Mỗi lần người dùng tải một file lên
IF OBJECT_ID(N'dbo.LanTaiLen', N'U') IS NULL
CREATE TABLE dbo.LanTaiLen (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    TenFile         NVARCHAR(260) NOT NULL,
    ThoiGianTai     DATETIME2(0)  NOT NULL DEFAULT SYSDATETIME(),
    SoDong          INT           NOT NULL,
    NgayBatDau      DATE          NOT NULL,
    NgayKetThuc     DATE          NOT NULL
);
GO

-- Database tạo từ phiên bản cũ (luồng ARIMA đã bỏ) có thêm các cột bắt buộc sau: cho phép để trống
IF COL_LENGTH(N'dbo.LanTaiLen', N'SoDongHuanLuyen') IS NOT NULL
    ALTER TABLE dbo.LanTaiLen ALTER COLUMN SoDongHuanLuyen INT NULL;
IF COL_LENGTH(N'dbo.LanTaiLen', N'SoDongKiemDinh') IS NOT NULL
    ALTER TABLE dbo.LanTaiLen ALTER COLUMN SoDongKiemDinh INT NULL;
GO

-- Dữ liệu tỷ giá theo ngày của từng lần tải lên
IF OBJECT_ID(N'dbo.TyGia', N'U') IS NULL
CREATE TABLE dbo.TyGia (
    Id          INT IDENTITY(1,1) PRIMARY KEY,
    LanTaiLenId INT           NOT NULL REFERENCES dbo.LanTaiLen(Id) ON DELETE CASCADE,
    Ngay        DATE          NOT NULL,
    GiaTri      DECIMAL(12,2) NOT NULL,
    CONSTRAINT UQ_TyGia UNIQUE (LanTaiLenId, Ngay)
);
GO

-- ===================== Học máy + tối ưu GA/SA (forecast_engine) =====================

-- Mỗi lần chạy pipeline học máy trên một lần tải lên
IF OBJECT_ID(N'dbo.PhienHocMay', N'U') IS NULL
CREATE TABLE dbo.PhienHocMay (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    LanTaiLenId     INT            NOT NULL REFERENCES dbo.LanTaiLen(Id) ON DELETE CASCADE,
    CheDo           NVARCHAR(10)   NOT NULL,             -- quick | full
    CheDoMucTieu    NVARCHAR(10)   NOT NULL,             -- diff | level
    TrangThai       NVARCHAR(20)   NOT NULL DEFAULT N'dang_cho',   -- dang_cho | dang_chay | xong | loi
    PhanTram        INT            NOT NULL DEFAULT 0,
    TienDo          NVARCHAR(400)  NULL,
    NhatKy          NVARCHAR(MAX)  NULL,
    ThoiGianTao     DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
    ThoiGianBatDau  DATETIME2(0)   NULL,
    ThoiGianKetThuc DATETIME2(0)   NULL,
    MoHinhChon      NVARCHAR(50)   NULL,
    BienTheChon     NVARCHAR(20)   NULL,
    NgayDuBao       DATE           NULL,
    DuBaoT1         DECIMAL(14,4)  NULL,
    KhoangDuoi95    DECIMAL(14,4)  NULL,
    KhoangTren95    DECIMAL(14,4)  NULL,
    XuHuong         NVARCHAR(20)   NULL,
    CanhBao         NVARCHAR(30)   NULL,
    KetQuaJson      NVARCHAR(MAX)  NULL,                 -- toàn bộ JSON mục 7.5
    Loi             NVARCHAR(MAX)  NULL
);
GO

-- Bảng xếp hạng 11 ứng viên của mỗi phiên
IF OBJECT_ID(N'dbo.BangXepHang', N'U') IS NULL
CREATE TABLE dbo.BangXepHang (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    PhienId         INT            NOT NULL REFERENCES dbo.PhienHocMay(Id) ON DELETE CASCADE,
    Hang            INT            NOT NULL,
    MoHinh          NVARCHAR(30)   NOT NULL,
    BienThe         NVARCHAR(20)   NOT NULL,
    MeanRMSE        FLOAT          NOT NULL,
    SdRMSE          FLOAT          NOT NULL,
    MAE             FLOAT          NOT NULL,
    MAPE            FLOAT          NOT NULL,
    Bias            FLOAT          NULL,
    DirAcc          FLOAT          NULL,
    CaiThienSoBaseline FLOAT       NULL,
    CaiThienSoRW    FLOAT          NULL,
    DmPvalueRW      FLOAT          NULL,
    DmPvalueARIMA   FLOAT          NULL,
    J_CV            FLOAT          NULL,
    SoSeed          INT            NOT NULL,
    SieuThamSo      NVARCHAR(MAX)  NULL,
    DuocChon        BIT            NOT NULL DEFAULT 0
);
GO

-- ===================== Quy trình bài NCKH (đặc tả v3) – chỉ THÊM bảng mới =====================

-- Mỗi lần chạy quy trình (một "job"): chế độ, phạm vi, tiến trình 12 công đoạn, Bảng 4.6
IF OBJECT_ID(N'dbo.PhienNCKH', N'U') IS NULL
CREATE TABLE dbo.PhienNCKH (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    LanTaiLenId     INT            NOT NULL REFERENCES dbo.LanTaiLen(Id) ON DELETE CASCADE,
    CheDo           NVARCHAR(20)   NOT NULL,             -- chay_thu | chay_day_du
    ThuatToan       NVARCHAR(100)  NOT NULL,             -- vd "ARIMA,ANN,RF,XGB"
    BienThe         NVARCHAR(50)   NOT NULL,             -- vd "Baseline,GA,SA"
    NguongTheoDoi   FLOAT          NOT NULL,             -- % (mặc định 0,10)
    NguongManh      FLOAT          NOT NULL,             -- % (mặc định 0,30)
    TrangThai       NVARCHAR(20)   NOT NULL DEFAULT N'uoc_tinh',  -- uoc_tinh | cho_xac_nhan | cho | dang_chay | xong | loi | huy
    PhanTram        FLOAT          NOT NULL DEFAULT 0,
    TienDoJson      NVARCHAR(MAX)  NULL,                 -- trạng thái 12 công đoạn
    UocTinhGiay     FLOAT          NULL,
    UocTinhJson     NVARCHAR(MAX)  NULL,
    YeuCauHuy       BIT            NOT NULL DEFAULT 0,
    ThoiGianTao     DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME(),
    ThoiGianBatDau  DATETIME2(0)   NULL,
    ThoiGianKetThuc DATETIME2(0)   NULL,
    Loi             NVARCHAR(MAX)  NULL,
    MoHinhChon      NVARCHAR(30)   NULL,
    BienTheChon     NVARCHAR(20)   NULL,
    NgayQuanSatCuoi DATE           NULL,
    TyGiaCuoi       DECIMAL(14,4)  NULL,
    NgayDuBao       DATE           NULL,
    DuBaoT1         DECIMAL(14,4)  NULL,
    DuBaoSD         FLOAT          NULL,
    DuBaoP05        DECIMAL(14,4)  NULL,
    DuBaoP95        DECIMAL(14,4)  NULL,
    ThayDoiPct      FLOAT          NULL,
    CanhBao         NVARCHAR(30)   NULL,
    KetQuaJson      NVARCHAR(MAX)  NULL
);
GO

-- Mỗi ứng viên của một lần chạy (ARIMA, ANN/RF/XGB × Baseline/GA/SA, Random walk để đối chiếu)
IF OBJECT_ID(N'dbo.NCKH_UngVien', N'U') IS NULL
CREATE TABLE dbo.NCKH_UngVien (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    PhienId         INT            NOT NULL REFERENCES dbo.PhienNCKH(Id) ON DELETE CASCADE,
    Khoa            NVARCHAR(30)   NOT NULL,             -- vd "XGB|SA", "ARIMA", "RW"
    MoHinh          NVARCHAR(30)   NOT NULL,
    BienThe         NVARCHAR(20)   NULL,
    SoLanChay       INT            NOT NULL,
    MAE             FLOAT          NOT NULL,
    RMSE            FLOAT          NOT NULL,
    MAPE            FLOAT          NOT NULL,
    SaiSoTB         FLOAT          NOT NULL,
    SaiSoChuan      FLOAT          NOT NULL,
    SdRMSE          FLOAT          NULL,
    DuBaoT1         DECIMAL(14,4)  NULL,
    DuBaoT1SD       FLOAT          NULL,
    DuBaoP05        DECIMAL(14,4)  NULL,
    DuBaoP95        DECIMAL(14,4)  NULL,
    ThayDoiPct      FLOAT          NULL,
    CanhBao         NVARCHAR(30)   NULL,
    DuocChon        BIT            NOT NULL DEFAULT 0,
    SieuThamSo      NVARCHAR(MAX)  NULL
);
GO

-- Dự báo từng ngày trên tập test của mỗi ứng viên (biểu đồ, bảng từng ngày, file CSV)
IF OBJECT_ID(N'dbo.NCKH_DuBaoTest', N'U') IS NULL
CREATE TABLE dbo.NCKH_DuBaoTest (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    PhienId         INT            NOT NULL REFERENCES dbo.PhienNCKH(Id) ON DELETE CASCADE,
    Khoa            NVARCHAR(30)   NOT NULL,
    Ngay            DATE           NOT NULL,
    ThucTe          DECIMAL(14,4)  NOT NULL,
    DuBao           DECIMAL(14,4)  NOT NULL,
    Duoi95          DECIMAL(14,4)  NULL,
    Tren95          DECIMAL(14,4)  NULL
);
GO

-- ===================== Bổ sung sau review phiên #9 – chỉ THÊM cột / bảng mới, không sửa dữ liệu cũ =====================

-- Địa chỉ IP người tạo phiên (giới hạn số phiên Chạy thử mỗi IP trong 1 giờ khi chia sẻ link công khai)
IF COL_LENGTH(N'dbo.PhienNCKH', N'DiaChiIP') IS NULL
    ALTER TABLE dbo.PhienNCKH ADD DiaChiIP NVARCHAR(64) NULL;
GO

-- Trạng thái lần tạo lịch sử dự báo giả lập (backtest) gần nhất của phiên
IF COL_LENGTH(N'dbo.PhienNCKH', N'BacktestTrangThai') IS NULL
    ALTER TABLE dbo.PhienNCKH ADD BacktestTrangThai NVARCHAR(400) NULL;
GO

-- Lịch sử dự báo T+1 giả lập (walk-forward) của mô hình được chọn – IsBacktest = 1, không phải dự báo thật
IF OBJECT_ID(N'dbo.NCKH_Backtest', N'U') IS NULL
CREATE TABLE dbo.NCKH_Backtest (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    PhienId         INT            NOT NULL REFERENCES dbo.PhienNCKH(Id) ON DELETE CASCADE,
    NgayDuBao       DATE           NOT NULL,             -- ngày được dự báo (T+1)
    NgayQuanSat     DATE           NOT NULL,             -- ngày cuối của dữ liệu dùng để huấn luyện (T)
    TyGiaQuanSat    DECIMAL(14,4)  NOT NULL,
    DuBaoT1         DECIMAL(14,4)  NOT NULL,             -- trung bình qua các seed
    ThucTe          DECIMAL(14,4)  NOT NULL,
    MoHinh          NVARCHAR(30)   NOT NULL,
    BienThe         NVARCHAR(20)   NULL,
    SoSeed          INT            NOT NULL,
    ThayDoiPct      FLOAT          NULL,
    CanhBao         NVARCHAR(30)   NULL,
    IsBacktest      BIT            NOT NULL DEFAULT 1,
    ThoiGianTao     DATETIME2(0)   NOT NULL DEFAULT SYSDATETIME()
);
GO
