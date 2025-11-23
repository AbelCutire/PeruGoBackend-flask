const express = require('express');
const cors = require('cors');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const app = express();
const PORT = process.env.PORT || 5000;
const JWT_SECRET = process.env.JWT_SECRET || 'fallback-secret-key-2024';

// Middleware
app.use(cors({
  origin: '*', // Permite todos los orígenes temporalmente
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  credentials: true
}));

app.use(express.json());

// Ruta de prueba principal
app.get('/', (req, res) => {
  res.json({ 
    message: 'Servidor backend operativo.',
    status: 'online',
    timestamp: new Date().toISOString()
  });
});

// ✅ RUTA DE STATUS PARA VERIFICAR
app.get('/auth/status', (req, res) => {
  res.json({ 
    message: 'Rutas de autenticación operativas',
    status: 'active',
    routes: [
      'POST /auth/login',
      'POST /auth/register', 
      'POST /auth/recover'
    ]
  });
});

// ✅ RUTA DE LOGIN
app.post('/auth/login', async (req, res) => {
  try {
    console.log('📨 Login request:', req.body);
    
    const { email, password } = req.body;

    // Validaciones
    if (!email || !password) {
      return res.status(400).json({ error: 'Email y contraseña son requeridos' });
    }

    // Buscar usuario
    const user = await prisma.user.findUnique({
      where: { email }
    });

    if (!user) {
      return res.status(400).json({ error: 'Usuario no encontrado' });
    }

    // Verificar contraseña
    const isPasswordValid = await bcrypt.compare(password, user.password);
    if (!isPasswordValid) {
      return res.status(400).json({ error: 'Contraseña incorrecta' });
    }

    // Generar token
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.json({
      message: 'Login exitoso',
      token,
      user: {
        id: user.id,
        email: user.email,
        username: user.username
      }
    });

  } catch (error) {
    console.error('❌ Error en login:', error);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// ✅ RUTA DE REGISTRO
app.post('/auth/register', async (req, res) => {
  try {
    console.log('📨 Register request:', req.body);
    
    const { email, password, username } = req.body;

    // Validaciones
    if (!email || !password) {
      return res.status(400).json({ error: 'Email y contraseña son requeridos' });
    }

    if (password.length < 6) {
      return res.status(400).json({ error: 'La contraseña debe tener al menos 6 caracteres' });
    }

    // Verificar si usuario existe
    const existingUser = await prisma.user.findUnique({
      where: { email }
    });

    if (existingUser) {
      return res.status(400).json({ error: 'Ya existe un usuario con este email' });
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 12);

    // Crear usuario
    const user = await prisma.user.create({
      data: {
        email,
        username: username || null,
        password: hashedPassword
      }
    });

    // Generar token
    const token = jwt.sign(
      { userId: user.id, email: user.email },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    res.status(201).json({
      message: 'Usuario registrado exitosamente',
      token,
      user: {
        id: user.id,
        email: user.email,
        username: user.username
      }
    });

  } catch (error) {
    console.error('❌ Error en registro:', error);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// ✅ RUTA DE RECUPERACIÓN
app.post('/auth/recover', async (req, res) => {
  try {
    console.log('📨 Recover request:', req.body);
    
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email es requerido' });
    }

    // Verificar si usuario existe
    const user = await prisma.user.findUnique({
      where: { email }
    });

    if (!user) {
      return res.status(404).json({ error: 'Usuario no encontrado' });
    }

    // Simular envío de email
    console.log(`📧 Email de recuperación simulado para: ${email}`);
    
    res.json({
      message: 'Se ha enviado un email con las instrucciones para recuperar tu contraseña',
      email: email
    });

  } catch (error) {
    console.error('❌ Error en recuperación:', error);
    res.status(500).json({ error: 'Error interno del servidor' });
  }
});

// Manejo de rutas no encontradas
app.use('*', (req, res) => {
  res.status(404).json({ 
    error: 'Ruta no encontrada',
    path: req.originalUrl,
    availableRoutes: [
      'GET /',
      'GET /auth/status', 
      'POST /auth/login',
      'POST /auth/register',
      'POST /auth/recover'
    ]
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Servidor corriendo en puerto ${PORT}`);
  console.log('✅ Rutas disponibles:');
  console.log('   GET  /');
  console.log('   GET  /auth/status');
  console.log('   POST /auth/login');
  console.log('   POST /auth/register');
  console.log('   POST /auth/recover');
});
