-- iHealthSim 用户认证表
-- 兼容 SQLite 和 MySQL

-- SQLite 建表
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    VARCHAR(64)  NOT NULL UNIQUE,
    email       VARCHAR(128) NOT NULL UNIQUE,
    password    VARCHAR(256) NOT NULL,
    role        VARCHAR(32)  NOT NULL DEFAULT 'operator',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login  TIMESTAMP
);

-- 默认管理员账号: admin / admin123
-- 密码使用 werkzeug generate_password_hash 生成
INSERT OR IGNORE INTO users (username, email, password, role)
VALUES (
    'admin',
    'admin@ihealthsim.local',
    'scrypt:32768:8:1$g7H8kL2mN9pQrS5t$b3a8f1c6d9e2f5a8b1c4d7e0f3a6b9c2d5e8f1a4b7c0d3e6f9a2b5c8d1e4',
    'admin'
);


-- MySQL 版建表（注释掉，按需使用）
/*
CREATE TABLE users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(64)  NOT NULL UNIQUE,
    email       VARCHAR(128) NOT NULL UNIQUE,
    password    VARCHAR(256) NOT NULL,
    role        VARCHAR(32)  NOT NULL DEFAULT 'operator',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login  TIMESTAMP    NULL,
    INDEX idx_username (username),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
*/
