import { bootstrapApplication } from '@angular/platform-browser';

import { App } from './app/app';
import { createAppConfig } from './app/app.config';
import { loadAppConfig } from './app/core/config/app-config';

loadAppConfig()
  .then((config) => bootstrapApplication(App, createAppConfig(config)))
  .catch((err) => {
    console.error(err);
    document.body.textContent = 'The portal could not start. Please contact the service desk.';
  });
