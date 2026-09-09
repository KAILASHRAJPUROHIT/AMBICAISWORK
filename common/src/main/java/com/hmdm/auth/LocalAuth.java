package com.hmdm.auth;

import com.google.inject.Inject;
import com.hmdm.persistence.UnsecureDAO;
import com.hmdm.persistence.UserDAO;
import com.hmdm.persistence.domain.User;
import com.hmdm.util.CryptoUtil;
import com.hmdm.util.PasswordUtil;

import javax.inject.Named;
import javax.inject.Singleton;

@Singleton
public class LocalAuth implements HmdmAuthInterface {

    private UnsecureDAO userDAO;

    @Inject
    public LocalAuth(UnsecureDAO userDAO) {
        this.userDAO = userDAO;
    }

    @Override
    public User findUser(String login) {
        return userDAO.findByLoginOrEmail(login);
    }

    @Override
    public boolean authenticate(User user, String password) {
        boolean legacyStored = !PasswordUtil.isPbkdf2Hash(user.getPassword());
        boolean legacyClient = PasswordUtil.looksLikeMd5Digest(password);
        boolean match = legacyStored
                ? PasswordUtil.passwordMatchLegacyDigest(legacyClient ? password : CryptoUtil.getMD5String(password), user.getPassword())
                : PasswordUtil.passwordMatchRaw(password, user.getPassword());
        if (!match) {
            userDAO.setUserLoginFailTime(user, System.currentTimeMillis());
        } else if (legacyStored && !legacyClient) {
            // Transparent one-time migration: only raw password authentication can be upgraded safely.
            user.setNewPassword(PasswordUtil.getHashFromRaw(password));
            userDAO.setUserNewPasswordUnsecure(user);
            user.setPassword(user.getNewPassword());
        }
        return match;
    }
}
