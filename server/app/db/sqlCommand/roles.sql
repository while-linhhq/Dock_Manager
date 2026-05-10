INSERT INTO "roles" ("id", "role_name", "description", "permissions") VALUES (1, 'admin', 'Full system access', '{"all": true}');
INSERT INTO "roles" ("id", "role_name", "description", "permissions") VALUES (2, 'operator', 'Port operations staff', '{"orders": true, "vessels": true, "detections": true}');
INSERT INTO "roles" ("id", "role_name", "description", "permissions") VALUES (3, 'viewer', 'Read-only access', '{"read": true}');
