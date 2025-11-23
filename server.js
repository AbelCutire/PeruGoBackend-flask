const express = require('express');
const cors = require('cors');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

const app = express();
const PORT = process.env.PORT || 5000;

// Configuración para SIEMPRE devolver JSON
app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  credentials: true
}));

app.use(express.json());

// Middleware para forzar respuestas JSON
app.use((req, res, next) => {
  // Sobrescribir el método send para asegurar JSON
  const originalSend = res.send;
  res.send = function(data) {
    // Si no es JSON, convertirlo
    if (typeof data === 'string' && !data.startsWith('{') && !data.startsWith('[')) {
      data = { message: data };
    }
    res.setHeader('Content-Type', 'application/json');
    return originalSend.call(this, JSON.stringify(data));
  };
  next();
});

// Manejo elegante de Prisma
let prisma = null;
let prismaError = null;

try {
  const { PrismaClient } = require('@prisma/client');
  prisma = new PrismaClient();
  console.log('✅ Prisma client initialized');
} catch (error) {
  prismaError = error.message;
  console.error('❌ Prisma initialization failed:', error.message);
  console.log('💡 Solution: Add DATABASE_URL to Railway variables');
}

// Ruta de prueba principal - SIEMPRE JSON
app.get('/', (req, res) => {
  res.json({ 
    message: 'Servidor backend operativo',
    status: 'online',
    timestamp: new Date().toISOString(),
    database: {
      available: !!prisma,
      error: prismaError
    },
    instructions: {
      database_setup: 'Add DATABASE_URL in Railway → Variables',
      test_login: 'Use test@test.com / 123456'
    }
  });
});

// Ruta de status - SIEMPRE JSON
app.get('/auth/status', (req, res) => {
  res.json({ 
    message: 'Rutas de autenticación operativas',
    status: 'active',
    database: {
      available: !!prisma,
      error: prismaError
    },
    routes: [
      'POST /auth/login',
      'POST /auth/register', 
      'POST /auth/recover'
    ]
  });
});

// Ruta de login - SIEMPRE JSON
app.post('/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;

    // Validaciones
    if (!email || !password) {
      return res.status(400).json({ error: 'Email y contraseña son requeridos' });
    }

    // Si Prisma no está disponible, usar modo simulación
    if (!prisma) {
      console.log('🔧 Usando modo simulación (sin base de datos)');
      
      // Credenciales de prueba
      if (email === 'test@test.com' && password === '123456') {
        const token = jwt.sign(
          { userId: 'test-user-id', email: email },
          process.env.JWT_SECRET || 'test-secret',
          { expiresIn: '24h' }
        );

        return res.json({
          message: 'Login exitoso (modo simulación)',
          token,
          user: {
            id: 'test-user-id',
            email: email,
            username: 'usuario_prueba'
          },
          simulated: true
        });
      } else {
        return res.status(400).json({ 
          error: 'Credenciales inválidas. Usa: test@test.com / 123456',
          simulated: true 
        });
      }
    }

    // Si Prisma está disponible, usar base de datos real
    const user = await prisma.user.findUnique({
      where: { email }
    });

    if (!user) {
      return res.status(400).json({ error: 'Usuario no encontrado' });
    }

    const isPasswordValid = await bcrypt.compare(password, user.password);
    if (!isPasswordValid) {
      return res.status(400).json({ error: 'Contraseña incorrecta' });
    }

    const token = jwt.sign(
      { userId: user.id, email: user.email },
      process.env.JWT_SECRET || 'fallback-secret',
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
    res.status(500).json({ 
      error: 'Error interno del servidor',
      details: error.message 
    });
  }
});

// Ruta de registro - SIEMPRE JSON
app.post('/auth/register', async (req, res) => {
  try {
    const { email, password, username } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: 'Email y contraseña son requeridos' });
    }

    if (password.length < 6) {
      return res.status(400).json({ error: 'La contraseña debe tener al menos 6 caracteres' });
    }

    // Si Prisma no está disponible
    if (!prisma) {
      const token = jwt.sign(
        { userId: 'new-user-id', email: email },
        process.env.JWT_SECRET || 'test-secret',
        { expiresIn: '24h' }
      );

      return res.status(201).json({
        message: 'Usuario registrado exitosamente (modo simulación)',
        token,
        user: {
          id: 'new-user-id',
          email: email,
          username: username || 'nuevo_usuario'
        },
        simulated: true
      });
    }

    // Con Prisma disponible
    const existingUser = await prisma.user.findUnique({
      where: { email }
    });

    if (existingUser) {
      return res.status(400).json({ error: 'Ya existe un usuario con este email' });
    }

    const hashedPassword = await bcrypt.hash(password, 12);

    const user = await prisma.user.create({
      data: {
        email,
        username: username || null,
        password: hashedPassword
      }
    });

    const token = jwt.sign(
      { userId: user.id, email: user.email },
      process.env.JWT_SECRET || 'fallback-secret',
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
    res.status(500).json({ 
      error: 'Error interno del servidor',
      details: error.message 
    });
  }
});

// Ruta de recuperación - SIEMPRE JSON
app.post('/auth/recover', async (req, res) => {
  try {
    const { email } = req.body;

    if (!email) {
      return res.status(400).json({ error: 'Email es requerido' });
    }

    // Simular siempre (no depende de base de datos)
    console.log(`📧 Email de recuperación simulado para: ${email}`);
    
    res.json({
      message: 'Se ha enviado un email con las instrucciones para recuperar tu contraseña',
      email: email,
      simulated: true
    });

  } catch (error) {
    console.error('❌ Error en recuperación:', error);
    res.status(500).json({ 
      error: 'Error interno del servidor',
      details: error.message 
    });
  }
});

// Health check - SIEMPRE JSON
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy',
    service: 'PeruGo Backend',
    timestamp: new Date().toISOString(),
    database: {
      available: !!prisma,
      error: prismaError
    }
  });
});

// Manejo de rutas no encontradas - SIEMPRE JSON
app.use('*', (req, res) => {
  res.status(404).json({ 
    error: 'Ruta no encontrada',
    path: req.originalUrl,
    availableRoutes: [
      'GET /',
      'GET /health',
      'GET /auth/status',
      'POST /auth/login',
      'POST /auth/register',
      'POST /auth/recover'
    ]
  });
});

// Error handler final - SIEMPRE JSON
app.use((error, req, res, next) => {
  console.error('💥 Error handler final:', error);
  res.status(500).json({ 
    error: 'Error interno del servidor',
    message: error.message,
    type: error.name
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Servidor corriendo en puerto ${PORT}`);
  console.log(`🔍 DATABASE_URL configurada: ${!!process.env.DATABASE_URL}`);
  console.log(`🔍 JWT_SECRET configurada: ${!!process.env.JWT_SECRET}`);
  console.log(`🔍 Prisma disponible: ${!!prisma}`);
  console.log('✅ Garantizado: Todas las respuestas serán JSON');
});