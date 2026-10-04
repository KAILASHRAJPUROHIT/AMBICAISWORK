package com.hmdm.persistence.mapper;

import com.hmdm.persistence.domain.SmtpOverride;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Select;

public interface SmtpOverrideMapper {
    @Select("SELECT * FROM smtpOverride WHERE id = 1")
    SmtpOverride get();

    @Insert("INSERT INTO smtpOverride (id, host, port, security, username, passwordEnc, fromAddress, updatedAt, updatedBy) " +
            "VALUES (1, #{host}, #{port}, #{security}, #{username}, #{passwordEnc}, #{fromAddress}, #{updatedAt}, #{updatedBy}) " +
            "ON CONFLICT (id) DO UPDATE SET host = EXCLUDED.host, port = EXCLUDED.port, security = EXCLUDED.security, " +
            "username = EXCLUDED.username, passwordEnc = EXCLUDED.passwordEnc, fromAddress = EXCLUDED.fromAddress, " +
            "updatedAt = EXCLUDED.updatedAt, updatedBy = EXCLUDED.updatedBy")
    void upsert(SmtpOverride o);

    @Delete("DELETE FROM smtpOverride WHERE id = 1")
    void clear();
}
