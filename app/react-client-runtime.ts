// Client-only stable React identity for the tunnelled Vinext development
// runtime. The server/RSC environments continue to use React's react-server
// export condition.
export * from "../node_modules/react/index.js";
import React from "../node_modules/react/index.js";

export default React;
