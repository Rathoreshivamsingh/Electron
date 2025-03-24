'use strict';

const electron = require('electron');
const path = require('path');
const fs = require('fs');
const log = require('electron-log');
const isDev = require('electron-is-dev');
const childProcess = require('child_process');
const http = require('http');




log.transports.file.level = 'info';
log.transports.console.level = 'info';

class ServerManager {
    constructor(app) {
        this.orthancProcess = null;
        this.pythonProcess = null;
        this.pythonServerUrl = 'http://localhost:5001';
        this.maxRetries = 30;
        this.retryInterval = 1000;
        this.app = app;
        this.stopPythonServer = this.stopPythonServer.bind(this);
    }


    getBasePath() {

        if (isDev) {
            return this.app.getAppPath();
        } else {
            
            return path.dirname(path.dirname(this.app.getPath('exe')));
        }
    }

    getResourcePath() {
        if (isDev) {
            return this.app.getAppPath();
        } else {
            return process.resourcesPath;
        }
    }

    getOrthancPath() {
        if (isDev) {
            return path.join(this.app.getAppPath(), 'servers', 'orthanc', 'Orthanc.exe');
        } else {
            return path.join(this.getBasePath(),'ScanOFe-win32-x64','resources', 'app', 'servers', 'orthanc', 'Orthanc.exe');
        }
    }


    getPythonPath() {
        const resourcePath = this.getResourcePath();
        return path.join(resourcePath, 'app', 'servers', 'orthanc', 'python', 'dist', 'python_server', 'python_server.exe');
    }

    async startOrthanc() {
        const orthancPath = this.getOrthancPath();
        const orthancConfig = isDev
            ? path.join(this.app.getAppPath(), 'servers', 'orthanc', 'orthanc.json')
            : path.join(this.getBasePath(), 'ScanOFe-win32-x64','resources', 'app', 'servers', 'orthanc', 'orthanc.json');
        if (!fs.existsSync(orthancPath)) {
            log.error(`Orthanc executable not found at ${orthancPath}`);
            return;
        }

        if (!fs.existsSync(orthancConfig)) {
            log.error(`Orthanc config not found at ${orthancConfig}`);
            return;
        }

        log.info('Starting Orthanc server...');

        const orthancDir = path.dirname(orthancPath);
        this.orthancProcess = childProcess.spawn(orthancPath, [orthancConfig], {
            cwd: orthancDir,
            detached: false,
            stdio: ['ignore', 'pipe', 'pipe']
        });

        this.orthancProcess.stdout.on('data', (data) => log.info(`Orthanc stdout: ${data}`));
        this.orthancProcess.stderr.on('data', (data) => log.error(`Orthanc stderr: ${data}`));
        this.orthancProcess.on('error', (err) => log.error('Failed to start Orthanc:', err));
        this.orthancProcess.on('exit', (code, signal) => {
            log.warn(`Orthanc exited with code ${code} and signal ${signal}`);
            this.orthancProcess = null;
        });

        log.info('Orthanc server started.');
    }

    stopOrthanc() {
        if (this.orthancProcess) {
            log.info('Stopping Orthanc server...');
            if (process.platform === 'win32') {
                childProcess.exec(`taskkill /PID ${this.orthancProcess.pid} /T /F`);
            } else {
                this.orthancProcess.kill();
            }
            this.orthancProcess = null;
            log.info('Orthanc server stopped.');
        }
    }

    stopPythonServer() {
        if (this.pythonProcess) {
            log.info('Stopping Python server...');
            if (process.platform === 'win32') {
                childProcess.exec(`taskkill /PID ${this.pythonProcess.pid} /T /F`);
            } else {
                process.kill(-this.pythonProcess.pid, 'SIGTERM');
            }
            this.pythonProcess = null;
            log.info('Python server stopped.');
        }
    }

    async startPythonServer() {
        try {
            

            const pythonExecutable = this.getPythonPath();
            const resourcePath = this.getResourcePath();
            const pythonDir = path.join(resourcePath, 'app', 'servers', 'orthanc', 'python');

            if (!fs.existsSync(pythonExecutable)) {
                log.error(`Python executable not found at ${pythonExecutable}`);
                throw new Error(`Python executable not found at ${pythonExecutable}`);
            }


            log.info('Starting Python server...');
            log.info(`Python Executable: ${pythonExecutable}`);
            log.info(`Working Directory: ${pythonDir}`);

            this.stopPythonServer();

            log.info('Starting Python server pre...');

            this.pythonProcess = childProcess.spawn(pythonExecutable, [], {
                cwd: pythonDir,
                detached: false,
                stdio: ['ignore', 'pipe', 'pipe'],
                env: { 
                    ...process.env, 
                    PYTHONUNBUFFERED: '1',
                    PYTHONPATH: pythonDir
                }
            });
            this.pythonProcess.stdout.on('data', (data) => log.info(`Python stdout: ${data}`));
            this.pythonProcess.stderr.on('data', (data) => log.error(`Python stderr: ${data}`));
            this.pythonProcess.on('error', (err) => log.error('Failed to start Python server:', err));
            this.pythonProcess.on('exit', (code, signal) => {
                log.warn(`Python server exited with code ${code} and signal ${signal}`);
                this.pythonProcess = null;
            });

            await this.waitForPythonServer();
            log.info('Python FastAPI server is running on http://localhost:5001');
            return true;
        } catch (error) {
            log.error('Error starting Python server:', error);
            this.stopPythonServer();
            throw error;
        }
    }

    async waitForPythonServer() {
        let retries = 0;
        while (retries < this.maxRetries) {
            try {
                await new Promise((resolve, reject) => {
                    http.get(this.pythonServerUrl, (res) => {
                        if (res.statusCode === 200) resolve();
                        else reject(new Error(`Server responded with status code ${res.statusCode}`));
                    }).on('error', reject);
                });
                return true;
            } catch (error) {
                retries++;
                if (retries >= this.maxRetries) {
                    throw new Error('Python server failed to start after maximum retries');
                }
                await new Promise((resolve) => setTimeout(resolve, this.retryInterval));
            }
        }
    }

    async startAll() {
        try {
            await this.startOrthanc();
            await this.startPythonServer();
            log.info('All servers started successfully.');
        } catch (error) {
            log.error('Error starting servers:', error);
            this.stopAll();
            throw error;
        }
    }

    stopAll() {
        this.stopOrthanc();
        this.stopPythonServer();
        log.info('All servers stopped.');
    }

    isRunning() {
        return {
            orthanc: this.orthancProcess !== null,
            python: this.pythonProcess !== null
        };
    }
}

class App {
    constructor() {
        this.mainWindow = null;
        this.app = electron.app;
        this.BrowserWindow = electron.BrowserWindow;
        this.serverManager = new ServerManager(this.app);
        
        this.init();
    }

    init() {

        const gotTheLock = this.app.requestSingleInstanceLock();
        if (!gotTheLock) {
            this.app.quit();
            return;
        }
 
        this.app.whenReady().then(() => {
            this.createWindow();
        });


        this.app.on('activate', () => {
            if (this.BrowserWindow.getAllWindows().length === 0) {
                this.createWindow();
            }
        });


        this.app.on('window-all-closed', async () => {
            log.info('All windows closed.');
            if (process.platform !== 'darwin') {
                await this.cleanup();
                this.app.quit();
            }
        });

        this.setupErrorHandlers();
    }

    getHtmlPath() {
        if (isDev) {
            return path.join(process.cwd(), 'build', 'index.html');
        } else {
 
            return path.join(this.app.getPath('exe'), '..', '..', 'ScanOFe-win32-x64','resources', 'app', 'build', 'index.html');
        }
    }

    async createWindow() {
        try {
            log.info('Starting servers...');
            await this.serverManager.startAll();
            log.info('Servers started successfully.');

            const htmlFilePath = this.getHtmlPath();
            log.info(`Loading HTML file from: ${htmlFilePath}`);
            
            if (!fs.existsSync(htmlFilePath)) {
                log.error(`HTML file does not exist at path: ${htmlFilePath}`);
                throw new Error('HTML file not found');
            }

            this.mainWindow = new this.BrowserWindow({
                width: 1920,
                height: 1080,
                show : false,
                
                webPreferences: {
                    nodeIntegration: true,
                    contextIsolation: false,
                    enableRemoteModule: false,
                    webSecurity: false,
                },
                backgroundColor: '#ffffff',
            });
           

            try {
                await this.mainWindow.loadFile(htmlFilePath);
            } catch (error) {
                log.error('Failed to load HTML file:', error);
                throw error;
            }

            setTimeout(() => {
                if (this.mainWindow && !this.mainWindow.isVisible()) {
                    log.info('Forcing window to show');
                    this.mainWindow.show();
                }
            }, 5000);


            this.mainWindow.on('closed', () => {
                this.mainWindow = null;
            });

            this.mainWindow.webContents.on('crashed', (event) => {
                log.error('Renderer process crashed:', event);
                this.cleanup();
                this.app.quit();
            });

        } catch (error) {
            log.error('Error during window creation:', error);
            await this.cleanup();
            this.app.exit(1);
        }
    }

    async cleanup() {
        log.info('Starting cleanup process...');
        try {
            if (this.mainWindow && !this.mainWindow.isDestroyed()) {
                this.mainWindow.hide();
                await this.mainWindow.close();
            }
            await this.serverManager.stopAll();
            log.info('Cleanup completed successfully.');
        } catch (error) {
            log.error('Error during cleanup:', error);
        }
    }

    setupErrorHandlers() {
        process.on('uncaughtException', async (error) => {
            log.error('Uncaught exception:', error);
            await this.cleanup();
            this.app.exit(1);
        });

        process.on('unhandledRejection', async (error) => {
            log.error('Unhandled rejection:', error);
            await this.cleanup();
            this.app.exit(1);
        });

        process.on('SIGINT', async () => {
            log.info('Received SIGINT signal');
            await this.cleanup();
            this.app.exit(0);
        });

        process.on('SIGTERM', async () => {
            log.info('Received SIGTERM signal');
            await this.cleanup();
            this.app.exit(0);
        });

    }
}


new App();