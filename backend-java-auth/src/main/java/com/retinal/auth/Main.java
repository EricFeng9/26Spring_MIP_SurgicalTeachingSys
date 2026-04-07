package com.retinal.auth;

import java.io.IOException;
import java.sql.SQLException;

public class Main {
    public static void main(String[] args) throws SQLException, IOException {
        int port = 8080;
        AuthHttpServer server = AuthHttpServer.createDefault(port);
        server.start();
    }
}
