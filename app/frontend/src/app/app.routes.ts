import { Routes } from '@angular/router';
import { authGuard } from './core/auth';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login').then((m) => m.Login) },
  {
    path: 'work',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/work').then((m) => m.Work),
  },
  {
    path: 'project/:id',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/project').then((m) => m.ProjectPage),
  },
  {
    path: 'run/:id',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/run').then((m) => m.RunPage),
  },
  {
    path: 'batch',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/batch').then((m) => m.BatchPage),
  },
  {
    path: 'settings',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/settings').then((m) => m.SettingsPage),
  },
  {
    path: 'history',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/history').then((m) => m.HistoryPage),
  },

  {
    path: 'help',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/help').then((m) => m.HelpPage),
  },
  {
    path: 'drive-connected',
    loadComponent: () => import('./pages/drive-connected').then((m) => m.DriveConnected),
  },
  { path: '', pathMatch: 'full', redirectTo: 'work' },
  { path: '**', redirectTo: 'work' },
];
