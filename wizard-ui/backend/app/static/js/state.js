// wizard/js/state.js

export const state = {
  admin: {
    username: "",
    email: "",
    password: "" // in-memory only, cleared after import
  },

  db_root: {
    host: "",
    port: 3306,
    user: "",
    password: "" // in-memory only
  },

  db_name: "",
  app_sql_user: "b2s_app",
  app_user_password: "", // in-memory only

  logging_db: {
    db_name: "",
    app_sql_user: "app_user",
    app_user_password: "" // in-memory only
  },

  services: [] // reserved for future use
};

export const stepStatus = {
  1: true,  // Welcome step is always valid
  2: false, // Admin
  3: false, // DB connection
  4: false, // App DB
  5: false, // Logging DB
  6: false  // Summary
};
